#!/bin/bash
# Send a chart request, wait until the chart step is on screen, then press Stop.
# The exact moment the e2e of 2026-09-05 took the app to the React error boundary (B1).
set -uo pipefail
RUN="${1:-1}"
export AGENT_BROWSER_SESSION=fq30a

agent-browser --session fq30a find role link click --name "New chat" >/dev/null
sleep 2
./.scratch/say.sh "Zeig mir die Ausgaben pro Kategorie 2025 als Balkendiagramm." >/dev/null

for i in $(seq 1 40); do
  seen=$(agent-browser --session fq30a eval --stdin <<'EOF' 2>&1 | tail -1
(() => (document.querySelector('[data-slot="chart-card"]') ? "CHART" : "no"))()
EOF
)
  case "$seen" in
    *CHART*) echo "chart step on screen after $i polls"; break ;;
  esac
  sleep 1
done

agent-browser --session fq30a find role button click --name "Stop"
sleep 4
agent-browser --session fq30a screenshot "/tmp/finquery-30a/stop-$RUN.png" >/dev/null
agent-browser --session fq30a eval --stdin <<'EOF'
(() => {
  const body = document.body.innerText;
  return {
    errorBoundary: body.includes("Something went wrong"),
    stoppedChip: body.includes("Stopped"),
    stoppedStep: body.includes("step was stopped before it finished"),
    thinking: /Thought for/.test(body),
    tail: body.slice(-400),
  };
})()
EOF
