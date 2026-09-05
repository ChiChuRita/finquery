#!/bin/bash
# Scroll the transcript itself, which is a stick-to-bottom container of its own.
set -uo pipefail
OFFSET="${1:-0}"
agent-browser --session fq30a eval --stdin <<EOF
(() => {
  const boxes = Array.from(document.querySelectorAll('div')).filter(
    (node) => node.scrollHeight > node.clientHeight + 40 && node.clientHeight > 200,
  );
  const box = boxes[0];
  if (!box) return 'no scroller';
  box.scrollTop = $OFFSET;
  return { scrollTop: box.scrollTop, scrollHeight: box.scrollHeight };
})()
EOF
