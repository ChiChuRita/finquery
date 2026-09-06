"""Headless renders of the kept charts, through the app's own chart runtime.

A chart that passes the self-check can still be a picture nobody can read, and the self-check
runs against recording stubs rather than against TanStack Charts. So every kept chart row is
drawn once, in the built runtime (`frontend/dist/chart-runtime.html`), in a sandboxed frame the
size of a real card, and the picture is what the vision judges of ticket 64 look at.

Nothing new is installed for it: a small HTTP server in this process serves the built bundle and
one job file per chart, and `agent-browser` in its usual headless mode drives Chrome.

    uv run python -m training.data.render --kept out/chart/kept.jsonl --out training/data/renders
    uv run python -m training.data.render --kept out/chart/kept.jsonl --theme both

The bundle is a build artifact and is not committed:

    npm --prefix frontend install && npm --prefix frontend run build

`--session` is a named agent-browser session, `ticket62` by default. Never close every session:
another agent may be holding one.
"""

import argparse
import json
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from training.data.schema import read_jsonl

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DIST = REPO / "frontend" / "dist"
RUNTIME = "chart-runtime.html"
PAGE = HERE / "render.html"
RENDERS = HERE / "renders"

WIDTH = 640
HEIGHT = 280
"""The size a chart card gives the frame (`CHART_HEIGHT` in `frontend/src/lib/chart-frame.ts`),
so a render is the picture the user would have seen and not a wider one."""

SESSION = "ticket62"
BROWSER = "agent-browser"

BUILD_FIRST = (
    f"{DIST / RUNTIME} is missing. The chart runtime is a build artifact and is not committed:\n"
    f"  npm --prefix frontend install\n"
    f"  npm --prefix frontend run build"
)

# The app's own colours, read out of `frontend/src/index.css` where `readTheme` reads them at
# run time. A render in the light theme is what a card looks like by default; the dark one is
# the same chart with the palette the dark theme resolves to.
THEMES: dict[str, dict[str, Any]] = {
    "light": {
        "color": "oklch(0.145 0 0)",
        "muted": "oklch(0.556 0 0)",
        "grid": "oklch(0.922 0 0)",
        "surface": "oklch(1 0 0)",
        "border": "oklch(0.922 0 0)",
        "palette": [
            "oklch(0.55 0.11 165)",
            "oklch(0.52 0.15 264)",
            "oklch(0.66 0.14 70)",
            "oklch(0.55 0.18 305)",
            "oklch(0.60 0.17 18)",
            "oklch(0.60 0.12 215)",
        ],
    },
    "dark": {
        "color": "oklch(0.985 0 0)",
        "muted": "oklch(0.708 0 0)",
        "grid": "oklch(1 0 0 / 10%)",
        "surface": "oklch(0.205 0 0)",
        "border": "oklch(1 0 0 / 10%)",
        "palette": [
            "oklch(0.66 0.13 165)",
            "oklch(0.64 0.15 264)",
            "oklch(0.67 0.14 70)",
            "oklch(0.64 0.16 305)",
            "oklch(0.65 0.17 18)",
            "oklch(0.66 0.11 215)",
        ],
    },
}


class RenderFailed(RuntimeError):
    """The bundle is missing, or the browser could not be driven at all."""


class Handler(SimpleHTTPRequestHandler):
    """Two roots and one header.

    The jobs and this page come first, the built bundle behind them. The header is the one the
    sandbox costs (ADR 0009): the frame has an opaque origin, so it fetches its own entry bundle
    as a cross-origin request and the built app answers exactly this way.
    """

    roots: tuple[Path, ...] = ()

    def translate_path(self, path: str) -> str:
        relative = path.split("?", 1)[0].split("#", 1)[0].lstrip("/")
        for root in self.roots:
            candidate = (root / relative).resolve()
            if root.resolve() in candidate.parents or candidate == root.resolve():
                if candidate.exists():
                    return str(candidate)
        return str((self.roots[-1] / relative).resolve())

    def end_headers(self) -> None:
        self.send_header("access-control-allow-origin", "*")
        self.send_header("cache-control", "no-store")
        super().end_headers()

    def log_message(self, *_args: Any) -> None:  # noqa: ANN401 - the server is not the output
        return


@dataclass
class Job:
    """One chart to draw: what the card would post into the frame."""

    id: str
    household: str
    shape: str
    language: str
    theme: str
    payload: dict[str, Any]

    @property
    def name(self) -> str:
        return self.id if self.theme == "light" else f"{self.id}-{self.theme}"


def jobs_of(kept: list[dict[str, Any]], themes: list[str]) -> list[Job]:
    """One job per kept chart row per theme, in the order the rows came."""
    jobs: list[Job] = []
    for row in kept:
        candidate = row["candidate"]
        for theme in themes:
            jobs.append(
                Job(
                    id=candidate["id"],
                    household=candidate["household"],
                    shape=candidate["shape"],
                    language=candidate["language"],
                    theme=theme,
                    payload={
                        "title": candidate["plan"]["title"],
                        "language": candidate["language"],
                        "code": candidate["code"],
                        "rows": row["rows"],
                        "theme": THEMES[theme],
                    },
                )
            )
    return jobs


def _browser(session: str, *arguments: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [BROWSER, "--session", session, *arguments],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


def render(jobs: list[Job], out: Path, *, session: str = SESSION, port: int = 0) -> list[dict[str, Any]]:
    """Draw every job and write one PNG each. Returns the manifest rows."""
    if not (DIST / RUNTIME).exists():
        raise RenderFailed(BUILD_FIRST)
    if shutil.which(BROWSER) is None:
        raise RenderFailed(f"{BROWSER} is not installed. `npm i -g agent-browser && agent-browser install`.")
    # agent-browser reads a leading dot as a CSS selector, so the target is always absolute.
    out = out.resolve()
    out.mkdir(parents=True, exist_ok=True)

    with TemporaryDirectory(prefix="finquery-render-") as temporary:
        served = Path(temporary)
        (served / "jobs").mkdir()
        shutil.copyfile(PAGE, served / "render.html")
        for job in jobs:
            (served / "jobs" / f"{job.name}.json").write_text(
                json.dumps(job.payload, ensure_ascii=False), encoding="utf-8"
            )
        handler = partial(Handler, directory=str(served))
        Handler.roots = (served, DIST)
        server = ThreadingHTTPServer(("127.0.0.1", port), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            return _draw(jobs, out, base=base, session=session)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


def _draw(jobs: list[Job], out: Path, *, base: str, session: str) -> list[dict[str, Any]]:
    manifest: list[dict[str, Any]] = []
    started = _browser(session, "open", f"{base}/render.html?job={jobs[0].name}")
    if started.returncode != 0:
        raise RenderFailed(f"{BROWSER} could not open a page: {started.stderr.strip() or started.stdout.strip()}")
    _browser(session, "set", "viewport", str(WIDTH), str(HEIGHT))
    for index, job in enumerate(jobs):
        target = out / f"{job.name}.png"
        target.unlink(missing_ok=True)
        if index:
            _browser(session, "navigate", f"{base}/render.html?job={job.name}")
        else:
            _browser(session, "reload")
        _browser(session, "wait", "--fn", "window.finqueryRenderState !== 'loading'")
        state = _browser(session, "eval", "window.finqueryRenderState + '|' + window.finqueryRenderMessage")
        answer = state.stdout.strip().strip('"')
        painted = answer.startswith("ready")
        if painted:
            _browser(session, "screenshot", str(target))
        manifest.append(
            {
                "id": job.id,
                "household": job.household,
                "shape": job.shape,
                "language": job.language,
                "theme": job.theme,
                "file": target.name if painted and target.exists() else None,
                "width": WIDTH,
                "height": HEIGHT,
                "bytes": target.stat().st_size if painted and target.exists() else 0,
                "error": None if painted else (answer.split("|", 1)[-1] or "the frame never painted"),
            }
        )
    (out / "manifest.json").write_text(
        json.dumps({"width": WIDTH, "height": HEIGHT, "renders": manifest}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render every kept chart through the real runtime.")
    parser.add_argument("--kept", type=Path, required=True, help="the gate's kept.jsonl for a chart batch")
    parser.add_argument("--out", type=Path, default=RENDERS)
    parser.add_argument("--theme", choices=("light", "dark", "both"), default="light")
    parser.add_argument("--session", default=SESSION, help="the agent-browser session name")
    parser.add_argument("--limit", type=int, default=None, help="render only the first n charts")
    args = parser.parse_args(argv)

    kept = read_jsonl(args.kept)
    if args.limit is not None:
        kept = kept[: args.limit]
    if not kept:
        print(f"{args.kept} holds no kept charts", file=sys.stderr)
        return 1
    themes = ["light", "dark"] if args.theme == "both" else [args.theme]
    try:
        manifest = render(jobs_of(kept, themes), args.out, session=args.session)
    except RenderFailed as exc:
        print(str(exc), file=sys.stderr)
        return 2
    drawn = [row for row in manifest if row["file"]]
    print(f"{len(drawn)} of {len(manifest)} rendered to {args.out}")
    for row in manifest:
        if not row["file"]:
            print(f"  no picture for {row['id']} ({row['theme']}): {row['error']}", file=sys.stderr)
    return 0 if len(drawn) == len(manifest) else 1


if __name__ == "__main__":
    raise SystemExit(main())
