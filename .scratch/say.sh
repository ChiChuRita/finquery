#!/bin/bash
# Type one message into the FinQuery composer and send it.
#
# `agent-browser fill` writes the DOM value without React noticing and the field stays
# desynced, so the text goes in through the native value setter plus an input event, which is
# what a real keystroke does (harness note of ticket 20). The whole snippet is an IIFE because
# every eval of a session shares one scope and a bare `const` collides on the second call.
set -euo pipefail
TEXT="$1"
export AGENT_BROWSER_SESSION=fq30a
TEXT_B64=$(printf '%s' "$TEXT" | base64)
cat <<EOF | agent-browser --session fq30a eval --stdin
(() => {
  const words = atob("$TEXT_B64");
  const box = document.querySelector('textarea');
  const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
  setter.call(box, words);
  box.dispatchEvent(new Event('input', { bubbles: true }));
  return "typed " + box.value.length + " chars";
})()
EOF
agent-browser --session fq30a find role button click --name "Submit"
