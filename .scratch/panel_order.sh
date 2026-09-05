#!/bin/bash
# The order of the drawn parts inside the newest assistant message.
set -uo pipefail
agent-browser --session fq30a eval --stdin <<'EOF'
(() => {
  const card = document.querySelector('[data-slot="chart-card"]');
  const box = card ? card.parentElement : null;
  if (!box) return ['no chart card'];
  return Array.from(box.children).map((node) => {
    if (node.matches('[data-slot="chart-card"]')) return 'chart';
    const text = (node.innerText || '').trim();
    if (/^Thought for|^Thinking/.test(text)) return 'thinking';
    return text.slice(0, 30);
  });
})()
EOF
