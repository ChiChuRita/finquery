"""The one suite that loads the real Gemma 4 models. Opt in with `FINQUERY_SMOKE=1`.

    FINQUERY_SMOKE=1 uv run pytest tests/test_local_smoke.py -s

It runs the same sanity check as `uv run finquery-check`, so a green run means both slots
answer, think, call a tool and read an image on this machine.
"""

import os

import pytest
from dotenv import load_dotenv

from finquery.local.check import format_report, run_check
from finquery.local.runtime import LocalStack
from finquery.settings import Settings

pytestmark = pytest.mark.skipif(os.environ.get("FINQUERY_SMOKE") != "1", reason="set FINQUERY_SMOKE=1 to load real models")


async def test_both_local_slots_answer_think_call_a_tool_and_see() -> None:
    load_dotenv()
    settings = Settings()
    assert settings.provider == "local", "the smoke test needs FINQUERY_PROVIDER=local"
    stack = LocalStack(settings)
    for slot in ("fast", "quality"):
        stack.downloads.ensure(slot)

    reports = await run_check(stack)

    print("\n" + format_report(reports))
    failed = [f"{r.slot}/{c.name}: {c.detail}" for r in reports for c in r.checks if not c.ok]
    assert not failed, failed
    assert all(report.error is None for report in reports)
