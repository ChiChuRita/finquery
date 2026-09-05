#!/bin/bash
# Wait until the page shows a phrase, then print the last part of what it says.
set -uo pipefail
NEEDLE="$1"
TRIES="${2:-60}"
export AGENT_BROWSER_SESSION=fq30a
NEEDLE_B64=$(printf '%s' "$NEEDLE" | base64)
for i in $(seq 1 "$TRIES"); do
  seen=$(cat <<EOF | agent-browser --session fq30a eval --stdin 2>&1 | tail -1
(() => (document.body.innerText.includes(atob("$NEEDLE_B64")) ? "FOUND" : "no"))()
EOF
)
  case "$seen" in
    *FOUND*) echo "found after $i polls"; exit 0 ;;
  esac
  sleep 2
done
echo "not found after $TRIES polls"
exit 1
