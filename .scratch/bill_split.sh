#!/bin/bash
# Drop a receipt photo into a fresh chat, wait for the split proposal, press Apply, and read
# the legs back off the Transactions API. Three of these is the B3 check.
set -uo pipefail
FIXTURE="$1"
RUN="$2"
PROFILE=58f5ab7707024b7f8399f7cef7ef4105
export AGENT_BROWSER_SESSION=fq30a

agent-browser --session fq30a find role link click --name "New chat" >/dev/null
sleep 2
./.scratch/attach.sh "$FIXTURE" image/png | tail -1
./.scratch/say.sh "Hier ist ein Kassenbon." >/dev/null

./.scratch/await_text.sh "Apply" 120 || { echo "no proposal"; exit 1; }
agent-browser --session fq30a screenshot "/tmp/finquery-30a/bill-$RUN-proposed.png" >/dev/null
agent-browser --session fq30a find role button click --name "Apply"
./.scratch/await_text.sh "These bookings have changed" 40 || echo "no applied note"
sleep 2
agent-browser --session fq30a screenshot "/tmp/finquery-30a/bill-$RUN-applied.png" >/dev/null
agent-browser --session fq30a eval --stdin <<'EOF'
(() => {
  const body = document.body.innerText;
  return {
    applied: body.includes("Applied"),
    note: body.includes("These bookings have changed"),
    failure: /did not change|was not written|are still there/.test(body),
  };
})()
EOF
echo "--- legs on the Transactions page ---"
curl -s "http://127.0.0.1:8101/api/transactions?profile_id=$PROFILE&limit=1000" > /tmp/finquery-30a/rows.json
python3 .scratch/legs.py
