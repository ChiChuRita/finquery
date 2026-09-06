"""The sanity check: does each local model answer, think, call a tool and see an image.

Run before a demo, from the CLI (`uv run finquery-check`) or from the Settings page. It covers
the fast slot and every local chat model whose weights are on disk, one at a time (the two chat
models share a seat), so it is the slowest thing in the project and the fastest way to find out
that the local setup is broken.

The CLI then does the thing the demo depends on and the per-model checks cannot show: it holds
the shipped pair, Gemma 4 E4B and Gemma 4 12B, in memory at the same time and reports the
headroom left (`check_pair`).
"""

import asyncio
import os
import struct
import subprocess
import sys
import time
import zlib
from dataclasses import asdict, dataclass, field
from typing import Literal

from pydantic_ai import Agent, BinaryContent
from pydantic_ai.messages import ThinkingPart, ToolCallPart

from finquery.local.catalog import ADAPTER_NAMES, LOCAL_CHAT_MODELS, LOCAL_FAST, ModelSpec
from finquery.local.runtime import LocalStack

CheckName = Literal["answer", "thinking", "tool_call", "vision"]

GIGABYTE = 1e9

METAL_SHARE = 0.75
"""How much of the machine's memory Metal lets this process hold. Measured on the 24 GB M4 Pro
of ADR 0006: a working set of 18.2 GB, which is 0.76, taken down to 0.75 so the number the
check prints is never larger than the machine really allows."""

HEADROOM_FLOOR = 1.0
"""Gigabytes that have to be left over for the pair to count as fitting. llama.cpp allocates
the whole KV cache when it loads, so this is room for the compute buffers of a full prompt and
for the projector of an image, not for the weights."""

FALLBACK_N_CTX = 16384
"""The context to fall back to when the pair does not fit at the configured one. Lowering the
chat model's context is preferred over evicting the fast slot: E4B is where every adapter
attaches and it is resident for a reason (ADR 0006, ADR 0013)."""


@dataclass
class Check:
    name: CheckName
    ok: bool
    detail: str
    seconds: float
    output_tokens: int = 0

    @property
    def tokens_per_second(self) -> float | None:
        return round(self.output_tokens / self.seconds, 1) if self.seconds > 0 and self.output_tokens else None


@dataclass
class AdapterCheck:
    name: str
    attached: bool
    note: str | None


@dataclass
class SlotReport:
    key: str
    label: str
    model: str
    load_seconds: float | None = None
    checks: list[Check] = field(default_factory=list)
    adapters: list[AdapterCheck] = field(default_factory=list)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and all(check.ok for check in self.checks)


def solid_png(rgb: tuple[int, int, int], size: int = 64) -> bytes:
    """A one-colour PNG, so the vision check needs no fixture file."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    header = struct.pack(">2I5B", size, size, 8, 2, 0, 0, 0)
    rows = b"".join(b"\x00" + bytes(rgb) * size for _ in range(size))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")


def _parts(result: object) -> list[object]:
    return [part for message in result.all_messages() for part in getattr(message, "parts", [])]  # type: ignore[attr-defined]


async def check_slot(stack: LocalStack, spec: ModelSpec) -> SlotReport:
    """Load one local model into its seat and put it through all four checks."""
    model = stack.resolve(spec)
    report = SlotReport(key=spec.key, label=spec.label, model=model.model_name)
    try:
        # Answer and thinking are two checks on one run: the thinking is what produced the answer.
        report.checks.extend(await _answer_and_thinking(model))
        report.checks.append(await _tool_call(model))
        report.checks.append(await _vision(model))
        report.load_seconds = next((s.load_seconds for s in stack.status() if s.key == spec.key), None)
        report.adapters = _adapters(stack, spec)
    except Exception as exc:  # noqa: BLE001 - the report is the result; a raise would lose the rest
        report.error = f"{type(exc).__name__}: {exc}"
    return report


#: Multi-step and about money: both models answer a one-step sum straight out even with
#: thinking enabled, so a trivial question proves nothing about the thought channel.
#: 12.40 + 3.60 - 5 = 11.
ARITHMETIC = "A shop charges 12.40 EUR, then 3.60 EUR, then refunds 5.00 EUR. What is the net amount?"
CAREFUL = "You are a careful assistant. Work the problem out in your thinking first, then answer in one short sentence."


async def _answer_and_thinking(model: object) -> list[Check]:
    agent: Agent[None, str] = Agent(model, instructions=CAREFUL)  # type: ignore[arg-type]
    started = time.monotonic()
    # Whether the model opens the thought channel is its own choice, so one miss at temperature
    # 1.0 is not a broken setup. Two tries is enough to tell a choice from a wiring problem.
    for attempt in (1, 2):
        result = await agent.run(ARITHMETIC)
        thinking = "".join(part.content for part in _parts(result) if isinstance(part, ThinkingPart)).strip()
        if thinking or attempt == 2:
            break
    seconds = round(time.monotonic() - started, 2)
    text = result.output.strip()
    return [
        Check(
            name="answer",
            ok="11" in text,
            detail=text[:120] or "empty answer",
            seconds=seconds,
            output_tokens=result.usage.output_tokens,
        ),
        Check(
            name="thinking",
            ok=bool(thinking),
            detail=f"{len(thinking)} characters of reasoning" if thinking else "no thinking part in the response",
            seconds=seconds,
        ),
    ]


async def _tool_call(model: object) -> Check:
    called: list[str] = []
    agent: Agent[None, str] = Agent(
        model,  # type: ignore[arg-type]
        instructions="Use the tools to answer. Never guess a balance.",
    )

    @agent.tool_plain
    def account_balance(account: str) -> str:
        """The current balance of one account in EUR.

        Args:
            account: The account name, for example "checking".
        """
        called.append(account)
        return "1234.56 EUR"

    started = time.monotonic()
    result = await agent.run("What is the balance of my checking account?")
    calls = [part.tool_name for part in _parts(result) if isinstance(part, ToolCallPart)]
    return Check(
        name="tool_call",
        ok=bool(called),
        detail=f"called {calls}" if calls else "the model answered without calling the tool",
        seconds=round(time.monotonic() - started, 2),
        output_tokens=result.usage.output_tokens,
    )


async def _vision(model: object) -> Check:
    agent: Agent[None, str] = Agent(model)  # type: ignore[arg-type]
    started = time.monotonic()
    result = await agent.run(
        [
            "This image is one solid colour. Which colour? Answer with the single colour word only.",
            BinaryContent(data=solid_png((220, 20, 20)), media_type="image/png"),
        ]
    )
    answer = result.output.strip().lower()
    return Check(
        name="vision",
        ok="red" in answer,
        detail=f"answered {result.output.strip()[:60]!r} for a red image",
        seconds=round(time.monotonic() - started, 2),
        output_tokens=result.usage.output_tokens,
    )


def _adapters(stack: LocalStack, spec: ModelSpec) -> list[AdapterCheck]:
    """Attach and detach every registered adapter, reporting what actually happened."""
    if spec.seat != "fast":
        return []
    loaded = stack.slot("fast")
    results: list[AdapterCheck] = []
    for name in ADAPTER_NAMES:
        with stack.adapters.attached_to(name, loaded) as note:
            results.append(AdapterCheck(name=name, attached=note is None, note=note.text if note else None))
    return results


def checkable(stack: LocalStack) -> tuple[ModelSpec, ...]:
    """The fast slot, plus every local chat model whose files are on disk.

    A chat model that was never downloaded is not a failure to report, it is a model this
    machine does not have; the models card is where that is said.
    """
    chat = tuple(spec for spec in LOCAL_CHAT_MODELS if stack.downloads.ready(spec.key))
    return (LOCAL_FAST, *chat)


async def run_check(stack: LocalStack, specs: tuple[ModelSpec, ...] | None = None) -> list[SlotReport]:
    return [await check_slot(stack, spec) for spec in (specs if specs is not None else checkable(stack))]


@dataclass
class PairReport:
    """The two shipped local models resident at once: do they fit, and with how much room."""

    models: list[str]
    n_ctx: int
    """The context the chat model ended up loaded at."""
    ok: bool
    resident_gb: float
    working_set_gb: float
    headroom_gb: float
    note: str | None = None
    """What to do about it, when the pair only fit after falling back."""
    error: str | None = None


def working_set_bytes() -> int:
    """What Metal lets this process hold: the machine's memory times `METAL_SHARE`."""
    return int(os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE") * METAL_SHARE)


def resident_bytes() -> int:
    """How much memory this process holds right now.

    Through `ps` because the stdlib only offers the peak (`resource.ru_maxrss`), and a peak
    would carry the first attempt's 32k weights into the number the second attempt reports.
    No new dependency for one figure.
    """
    out = subprocess.run(  # noqa: S603 - fixed argv, our own pid
        ["ps", "-o", "rss=", "-p", str(os.getpid())], capture_output=True, text=True, check=True
    )
    return int(out.stdout.strip()) * 1024


async def check_pair(stack: LocalStack, chat: ModelSpec | None = None) -> PairReport:
    """Hold Gemma 4 E4B and the shipped chat model at once, and report the headroom.

    This is the one thing the per-model checks cannot show: they run a seat at a time, and the
    demo runs both. Gemma 4 12B plus E4B was measured at about 12.9 GB at 32k
    (`bench/results/20260906-local-tokens-per-second.md`), inside the 18.2 GB this Mac allows.

    If the pair does not fit at the configured context, the chat model is loaded again at 16k
    rather than the fast slot being evicted: every adapter attaches to E4B and a sub-agent runs
    behind almost every turn, so the seat to give up context is the chat one. The report says
    so, and `FINQUERY_LOCAL_N_CTX` is the setting that makes it permanent.
    """
    spec = chat if chat is not None else LOCAL_CHAT_MODELS[0]
    models = [LOCAL_FAST.label, spec.label]
    working_set = working_set_bytes() / GIGABYTE
    configured = stack.n_ctx
    note: str | None = None
    for n_ctx in dict.fromkeys((configured, FALLBACK_N_CTX)):
        last = n_ctx == FALLBACK_N_CTX
        stack.n_ctx = n_ctx
        try:
            async with stack.holding("fast", LOCAL_FAST), stack.holding("chat", spec):
                resident = resident_bytes() / GIGABYTE
        except Exception as exc:  # noqa: BLE001 - out of memory is a result to report, not a crash
            failure = f"{type(exc).__name__}: {exc}"
            if last:
                return PairReport(models, n_ctx, False, 0.0, round(working_set, 1), 0.0, note, failure)
            stack.unload("chat")
            note = f"At {configured // 1024}k the pair did not load ({failure}), so the chat seat was tried at 16k."
            continue
        headroom = working_set - resident
        if headroom >= HEADROOM_FLOOR or last:
            if last and n_ctx != configured:
                note = (
                    f"{(note or '').rstrip()} Set FINQUERY_LOCAL_N_CTX=16384 to keep both resident; "
                    "the fast slot stays loaded either way."
                ).strip()
            return PairReport(models, n_ctx, headroom >= HEADROOM_FLOOR, round(resident, 1), round(working_set, 1), round(headroom, 1), note)
        stack.unload("chat")
        note = (
            f"At {configured // 1024}k the pair left only {headroom:.1f} GB of the {working_set:.1f} GB "
            f"Metal working set, so the chat seat was tried at 16k."
        )
    raise AssertionError("check_pair always returns from the loop")


def format_pair(report: PairReport) -> str:
    """The pair report as the CLI prints it, under the per-model checks."""
    mark = "ok  " if report.ok else "FAIL"
    lines = [f"[{mark}] {' plus '.join(report.models)} resident together at {report.n_ctx // 1024}k context"]
    if report.error:
        lines.append(f"         error: {report.error}")
    else:
        lines.append(
            f"         {report.resident_gb} GB resident of a {report.working_set_gb} GB working set, "
            f"{report.headroom_gb} GB headroom"
        )
    if report.note:
        lines.append(f"         {report.note}")
    return "\n".join(lines)


def format_report(reports: list[SlotReport]) -> str:
    lines: list[str] = []
    for report in reports:
        mark = "ok  " if report.ok else "FAIL"
        load = f", loaded in {report.load_seconds}s" if report.load_seconds else ""
        lines.append(f"[{mark}] {report.label}: {report.model}{load}")
        if report.error:
            lines.append(f"         error: {report.error}")
        for check in sorted(report.checks, key=lambda c: c.name):
            rate = f", {check.tokens_per_second} tok/s" if check.tokens_per_second else ""
            lines.append(f"         {'ok ' if check.ok else 'FAIL'} {check.name:<9} {check.seconds}s{rate}  {check.detail}")
        for adapter in report.adapters:
            state = "attached" if adapter.attached else f"base weights ({adapter.note})"
            lines.append(f"         --  adapter {adapter.name}: {state}")
    lines.append("all checks passed" if all(r.ok for r in reports) else "some checks failed")
    return "\n".join(lines)


def report_json(reports: list[SlotReport]) -> list[dict[str, object]]:
    """The Settings page's shape: the dataclasses plus the derived fields."""
    return [
        {
            **asdict(report),
            "ok": report.ok,
            "checks": [{**asdict(check), "tokens_per_second": check.tokens_per_second} for check in report.checks],
        }
        for report in reports
    ]


def main() -> None:
    """`uv run finquery-check`."""
    from dotenv import load_dotenv

    from finquery.settings import Settings

    load_dotenv()
    settings = Settings()
    if settings.provider != "local":
        print(f"FINQUERY_PROVIDER is {settings.provider}; the sanity check only covers the local models.")
        raise SystemExit(2)
    stack = LocalStack(settings)
    reports = asyncio.run(run_check(stack))
    print(format_report(reports))
    ok = all(report.ok for report in reports)
    # Then the pair the demo runs, both resident at once. The per-model checks left one chat
    # model in the seat; this loads the shipped one and says how much room is left.
    if stack.downloads.ready(LOCAL_CHAT_MODELS[0].key):
        pair = asyncio.run(check_pair(stack))
        print(format_pair(pair))
        ok = ok and pair.ok
    sys.exit(0 if ok else 1)
