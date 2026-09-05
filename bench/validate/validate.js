/**
 * The validation page: one gold datapoint at a time, Correct, Wrong or Unsure with a note.
 *
 * No build step and no framework. It reads `sample.json`, which
 * `uv run finquery-bench sample --seed N` writes, and keeps the labels in localStorage under a
 * key that carries the seed, so two samples never mix and a reload never loses a review.
 */

const STORE = 'finquery-bench-validation';
const VERDICTS = ['correct', 'wrong', 'unsure'];

const state = { sample: null, at: 0, labels: {} };

const euro = new Intl.NumberFormat('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const isEuroColumn = (name) => name === 'amount' || name.endsWith('_eur');
const isNumber = (value) => typeof value === 'number' && Number.isFinite(value);

function storeKey() {
  return `${STORE}-seed-${state.sample.seed}`;
}

function load() {
  try {
    state.labels = JSON.parse(localStorage.getItem(storeKey())) || {};
  } catch {
    state.labels = {};
  }
}

function save() {
  localStorage.setItem(storeKey(), JSON.stringify(state.labels));
}

function element(tag, properties = {}, children = []) {
  const node = Object.assign(document.createElement(tag), properties);
  for (const child of [].concat(children)) {
    if (child !== null && child !== undefined && child !== false) node.append(child);
  }
  return node;
}

function cell(value, column) {
  if (value === null || value === undefined) return element('td', { className: 'muted', textContent: 'no value' });
  if (isNumber(value)) {
    const text = isEuroColumn(column) ? `${euro.format(value)} EUR` : String(value);
    return element('td', { className: 'num', textContent: text });
  }
  return element('td', { textContent: String(value) });
}

function rowsTable(columns, rows) {
  const shown = rows.slice(0, 40);
  const head = element(
    'tr',
    {},
    columns.map((column) => element('th', { textContent: column, className: isEuroColumn(column) ? 'num' : '' })),
  );
  const body = shown.map((row) => element('tr', {}, columns.map((column) => cell(row[column], column))));
  return element('div', {}, [
    element('table', {}, [element('thead', {}, [head]), element('tbody', {}, body)]),
    rows.length > shown.length
      ? element('p', { className: 'muted', textContent: `${rows.length - shown.length} more rows` })
      : null,
  ]);
}

function tag(text) {
  return element('span', { className: 'tag', textContent: text });
}

function renderPoint() {
  const point = state.sample.datapoints[state.at];
  const box = document.getElementById('point');
  box.replaceChildren();

  const tags = [
    tag(point.set),
    tag(point.kind),
    tag(`difficulty ${point.difficulty}`),
    tag(point.language),
    ...point.tags.map(tag),
    point.answer === 'none' ? tag('the data holds none') : null,
  ].filter(Boolean);

  box.append(
    element('div', { className: 'row muted' }, [
      element('code', { textContent: point.id }),
      element('span', { className: 'grow' }),
      element('span', { textContent: `${state.at + 1} of ${state.sample.datapoints.length}` }),
    ]),
    element('p', { className: 'question', textContent: point.question }),
    element('div', { className: 'tags' }, tags),
  );

  if (point.prefix && point.prefix.length) {
    box.append(
      element('p', { className: 'prefix', textContent: `Earlier in the conversation: ${point.prefix.join('  |  ')}` }),
    );
  }
  if (point.why) box.append(element('p', { className: 'why', textContent: point.why }));

  if (point.set === 'chart') {
    const alternatives = point.also.length ? `, or ${point.also.join(', ')}` : '';
    box.append(
      element('h2', { textContent: 'Chart' }),
      element('p', {
        textContent: `Shape: ${point.shape}${alternatives}. Columns: ${point.roles.join(', ')}.`,
      }),
    );
  }

  box.append(element('h2', { textContent: 'Reference SQL' }), element('pre', { textContent: point.sql }));
  box.append(
    element('h2', { textContent: `Expected rows (${point.gold.rows.length})` }),
    point.gold.rows.length
      ? rowsTable(point.gold.columns, point.gold.rows)
      : element('p', { className: 'muted', textContent: 'No rows, which is the expected answer here.' }),
  );
}

function renderVerdict() {
  const point = state.sample.datapoints[state.at];
  const label = state.labels[point.id] || {};
  for (const button of document.querySelectorAll('.verdict')) {
    button.classList.toggle('on', button.dataset.verdict === label.verdict);
  }
  document.getElementById('note').value = label.note || '';
}

function renderDots() {
  const dots = document.getElementById('dots');
  dots.replaceChildren(
    ...state.sample.datapoints.map((point, index) => {
      const label = state.labels[point.id] || {};
      const button = element('button', {
        className: `dot ${label.verdict || ''} ${index === state.at ? 'here' : ''}`,
        textContent: String(index + 1),
        title: point.id,
      });
      button.addEventListener('click', () => go(index));
      return button;
    }),
  );
}

function renderSummary() {
  const counts = { correct: 0, wrong: 0, unsure: 0 };
  for (const point of state.sample.datapoints) {
    const verdict = (state.labels[point.id] || {}).verdict;
    if (verdict) counts[verdict] += 1;
  }
  const total = state.sample.datapoints.length;
  const done = counts.correct + counts.wrong + counts.unsure;
  document.getElementById('summary').replaceChildren(
    element('div', { className: 'row' }, [
      element('strong', { textContent: `${done} of ${total} reviewed` }),
      element('span', { className: 'muted', textContent: `correct ${counts.correct}` }),
      element('span', { className: 'muted', textContent: `wrong ${counts.wrong}` }),
      element('span', { className: 'muted', textContent: `unsure ${counts.unsure}` }),
      element('span', { className: 'grow' }),
      element('span', {
        className: 'muted',
        textContent: done === total ? 'Every datapoint has a verdict.' : 'A set is trusted once every one has one.',
      }),
    ]),
  );
}

function render() {
  renderPoint();
  renderVerdict();
  renderDots();
  renderSummary();
}

function go(index) {
  state.at = Math.min(state.sample.datapoints.length - 1, Math.max(0, index));
  render();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function setVerdict(verdict) {
  const point = state.sample.datapoints[state.at];
  state.labels[point.id] = {
    verdict,
    note: document.getElementById('note').value.trim(),
    at: new Date().toISOString(),
  };
  save();
  render();
}

function saveNote() {
  const point = state.sample.datapoints[state.at];
  const label = state.labels[point.id] || { verdict: null };
  label.note = document.getElementById('note').value.trim();
  label.at = new Date().toISOString();
  state.labels[point.id] = label;
  save();
  renderSummary();
}

function exportLabels() {
  const payload = {
    seed: state.sample.seed,
    exported_at: new Date().toISOString(),
    labels: state.sample.datapoints.map((point) => ({
      id: point.id,
      set: point.set,
      kind: point.kind,
      question: point.question,
      verdict: (state.labels[point.id] || {}).verdict || null,
      note: (state.labels[point.id] || {}).note || '',
    })),
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
  const link = element('a', {
    href: URL.createObjectURL(blob),
    download: `validation-seed-${state.sample.seed}.json`,
  });
  document.body.append(link);
  link.click();
  link.remove();
}

async function start() {
  const response = await fetch('sample.json');
  state.sample = await response.json();
  load();
  document.getElementById('meta').textContent =
    `${state.sample.datapoints.length} datapoints, seed ${state.sample.seed}`;
  for (const button of document.querySelectorAll('.verdict')) {
    button.addEventListener('click', () => setVerdict(button.dataset.verdict));
  }
  document.getElementById('note').addEventListener('change', saveNote);
  document.getElementById('next').addEventListener('click', () => go(state.at + 1));
  document.getElementById('previous').addEventListener('click', () => go(state.at - 1));
  document.getElementById('export').addEventListener('click', exportLabels);
  document.getElementById('clear').addEventListener('click', () => {
    if (!window.confirm('Clear every label of this sample?')) return;
    state.labels = {};
    save();
    render();
  });
  document.addEventListener('keydown', (event) => {
    if (event.target.tagName === 'TEXTAREA') return;
    if (event.key === 'ArrowRight') go(state.at + 1);
    if (event.key === 'ArrowLeft') go(state.at - 1);
    const index = Number(event.key) - 1;
    if (VERDICTS[index]) setVerdict(VERDICTS[index]);
  });
  render();
}

start();
