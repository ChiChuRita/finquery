#!/bin/bash
# Type into the Transactions search box the way a keystroke does. `agent-browser fill` writes
# the DOM value without React noticing (harness note of ticket 20).
set -euo pipefail
TEXT_B64=$(printf '%s' "$1" | base64)
export AGENT_BROWSER_SESSION=fq30a
cat <<EOF | agent-browser --session fq30a eval --stdin
(() => {
  const box = document.querySelector('input[aria-label="Search descriptions and counterparties"]');
  if (!box) return "no search box";
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
  setter.call(box, atob("$TEXT_B64"));
  box.dispatchEvent(new Event("input", { bubbles: true }));
  return "searched " + box.value;
})()
EOF
