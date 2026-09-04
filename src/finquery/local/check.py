"""The sanity check: does each slot answer, think, call a tool and see an image.

Run before a demo, from the CLI (`uv run finquery-check`) or from the Settings page. It loads
both models, so it is the slowest thing in the project and the fastest way to find out that
the local setup is broken.
"""

import asyncio
import struct
import sys
import time
import zlib
from dataclasses import asdict, dataclass, field
from typing import Literal

from pydantic_ai import Agent, BinaryContent
from pydantic_ai.messages import ThinkingPart, ToolCallPart

from finquery.local.catalog import ADAPTER_NAMES
from finquery.local.runtime import LocalStack
from finquery.providers import MODEL_SLOTS, ModelSlot

CheckName = Literal["answer", "thinking", "tool_call", "vision"]


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
    slot: ModelSlot
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


async def check_slot(stack: LocalStack, slot: ModelSlot) -> SlotReport:
    """Load one slot and put it through all four checks."""
    model = stack.resolve(slot)
    report = SlotReport(slot=slot, model=model.model_name)
    try:
        # Answer and thinking are two checks on one run: the thinking is what produced the answer.
        report.checks.extend(await _answer_and_thinking(model))
        report.checks.append(await _tool_call(model))
        report.checks.append(await _vision(model))
        report.load_seconds = next((s.load_seconds for s in stack.status() if s.slot == slot), None)
        report.adapters = _adapters(stack, slot)
    except Exception as exc:  # noqa: BLE001 - the report is the result; a raise would lose the rest
        report.error = f"{type(exc).__name__}: {exc}"
    return report


#: Multi-step and about money: Gemma 4 answers a one-step sum straight out even with thinking
#: enabled, so a trivial question proves nothing about the thought channel. 12.40 + 3.60 - 5 = 11.
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


def _adapters(stack: LocalStack, slot: ModelSlot) -> list[AdapterCheck]:
    """Attach and detach every registered adapter, reporting what actually happened."""
    if slot != "fast":
        return []
    loaded = stack.slot("fast")
    results: list[AdapterCheck] = []
    for name in ADAPTER_NAMES:
        with stack.adapters.attached_to(name, loaded) as note:
            results.append(AdapterCheck(name=name, attached=note is None, note=note.text if note else None))
    return results


async def run_check(stack: LocalStack, slots: tuple[ModelSlot, ...] = MODEL_SLOTS) -> list[SlotReport]:
    return [await check_slot(stack, slot) for slot in slots]


def format_report(reports: list[SlotReport]) -> str:
    lines: list[str] = []
    for report in reports:
        mark = "ok  " if report.ok else "FAIL"
        load = f", loaded in {report.load_seconds}s" if report.load_seconds else ""
        lines.append(f"[{mark}] {report.slot}: {report.model}{load}")
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
    reports = asyncio.run(run_check(LocalStack(settings)))
    print(format_report(reports))
    sys.exit(0 if all(report.ok for report in reports) else 1)
