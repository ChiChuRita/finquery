"""Start the app in its own session for a browser verification.

`os.setsid` puts it in a process group of its own, so another agent's kill by name cannot
reach it and this agent can kill exactly the pid it started. Throwaway database, port from the
environment. Not part of the product: this is a harness for the verification loop.
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    port = os.environ.get("FINQUERY_PORT", "8085")
    db_path = os.environ.get("FINQUERY_DB_PATH", "/tmp/finquery-10/verify.db")
    log = Path(os.environ.get("FINQUERY_LOG", "/tmp/finquery-10/server.log"))
    log.parent.mkdir(parents=True, exist_ok=True)
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    environment = {**os.environ, "FINQUERY_PORT": port, "FINQUERY_DB_PATH": db_path}
    with log.open("w") as stream:
        process = subprocess.Popen(
            [sys.executable, "-m", "finquery.main"],
            cwd=ROOT,
            env=environment,
            stdout=stream,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    print(process.pid)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
