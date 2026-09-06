"""Check every `path:symbol` reference in the explainers.

Run from the repo root: `uv run python docs/explainers/check_refs.py`. Every backticked
`path:symbol` whose path has a file extension must name a file that exists, and every dotted
part of the symbol must occur in that file as a whole word. Bare `path` references (no symbol)
must exist too. Also refuses an em dash or an en dash anywhere in the files.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent

REFERENCE = re.compile(r"`([A-Za-z0-9_./-]+\.(?:py|ts|tsx|md|html|json|toml)):([A-Za-z_][A-Za-z0-9_.]*)`")
BARE_PATH = re.compile(r"`((?:src|frontend|bench|tests|training|docs|fixtures|scripts)/[A-Za-z0-9_./-]+\.[a-z]+)`")
DASHES = ("—", "–")


def main() -> int:
    failures: list[str] = []
    checked = 0
    for doc in sorted(HERE.glob("*.md")):
        text = doc.read_text(encoding="utf-8")
        for dash in DASHES:
            if dash in text:
                failures.append(f"{doc.name}: contains a dash character {dash!r}")
        for match in BARE_PATH.finditer(text):
            checked += 1
            if not (ROOT / match.group(1)).exists():
                failures.append(f"{doc.name}: missing file {match.group(1)}")
        for match in REFERENCE.finditer(text):
            checked += 1
            path, symbol = match.group(1), match.group(2)
            target = ROOT / path
            if not target.is_file():
                failures.append(f"{doc.name}: missing file {path} (for {symbol})")
                continue
            source = target.read_text(encoding="utf-8", errors="replace")
            for part in symbol.split("."):
                if not re.search(rf"\b{re.escape(part)}\b", source):
                    failures.append(f"{doc.name}: {path} does not define {part} (from {symbol})")
    for line in failures:
        print(line)
    print(f"{checked} references checked, {len(failures)} failures")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
