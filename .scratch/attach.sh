#!/bin/bash
# Put a fixture into the composer's file input, the way a drop does.
#
# `agent-browser upload` is off limits here, and a fetch from a second local port would need
# CORS, so the bytes travel inline as base64 and become a File in the page. React sees the same
# `change` event a real pick fires.
set -euo pipefail
PATH_TO_FILE="$1"
NAME=$(basename "$PATH_TO_FILE")
TYPE="${2:-text/csv}"
B64=$(base64 < "$PATH_TO_FILE" | tr -d '\n')
export AGENT_BROWSER_SESSION=fq30a
cat <<EOF | agent-browser --session fq30a eval --stdin
(() => {
  const binary = atob("$B64");
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  const picked = new File([bytes], "$NAME", { type: "$TYPE" });
  const transfer = new DataTransfer();
  transfer.items.add(picked);
  const field = document.querySelector('input[type=file]');
  if (!field) return "no file input";
  field.files = transfer.files;
  field.dispatchEvent(new Event("change", { bubbles: true }));
  return "attached " + picked.name + " (" + picked.size + " bytes)";
})()
EOF
