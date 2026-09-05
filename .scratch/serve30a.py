"""Start the FinQuery server for the ticket 30a browser check, in its own session.

Its own process group (`os.setsid`), so the check can stop exactly the process it started and
nothing else on this machine. Writes the pid to /tmp/finquery-30a/server.pid and the log to
/tmp/finquery-30a/server.log.
"""

import os
import pathlib
import subprocess
import sys

OUT = pathlib.Path("/tmp/finquery-30a")
OUT.mkdir(parents=True, exist_ok=True)
log = (OUT / "server.log").open("wb")

env = {
    **os.environ,
    "FINQUERY_PORT": "8101",
    "FINQUERY_DB_PATH": "/tmp/finquery-30a/finquery.sqlite3",
    "FINQUERY_PROVIDER": "openrouter",
}
process = subprocess.Popen(
    [sys.executable, "-m", "finquery.main"],
    cwd=str(pathlib.Path(__file__).resolve().parents[1]),
    env=env,
    stdout=log,
    stderr=subprocess.STDOUT,
    start_new_session=True,
)
(OUT / "server.pid").write_text(str(process.pid))
print(process.pid)
