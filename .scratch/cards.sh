#!/bin/bash
# How many Question cards the transcript holds, and what the end of it says.
set -uo pipefail
agent-browser --session fq30a eval --stdin <<'EOF'
(() => {
  const body = document.body.innerText;
  return {
    cards: (body.match(/Which category do these belong to\?/g) || []).length,
    tail: body.slice(-900),
  };
})()
EOF
