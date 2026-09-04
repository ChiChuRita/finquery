"""The in-process self-check: run the generated chart code before the browser ever sees it.

The code the chart sub-agent writes is a JavaScript function body over an allowlisted set of
globals (see `docs/chart-runtime.md`). Here it is compiled and run inside QuickJS against stub
globals that record what was asked for instead of drawing anything, and the recording is judged
against the house rules. Every finding is written for the model to read and fix, so the same
strings are the repair instructions.

The stub is the only place that knows the shape of a TanStack Charts definition. It deliberately
does not render: a browser renders, this checks intent.
"""

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any

import quickjs

from finquery.chart.shapes import FAMILY_MARKS, MAX_SERIES, MAX_SLICES, SHAPES, Shape

# The globals the code may use. The browser runtime (frontend/src/chart-runtime/globals.ts)
# provides the same names for real. Each side pairs its own names with its own values, so only
# the membership of the two lists has to match, and a name missing on either side fails loudly:
# in the check as a ReferenceError finding, in the browser as an error on the card.
GLOBAL_NAMES = (
    "defineChart",
    "lineY",
    "areaY",
    "barY",
    "barX",
    "link",
    "rect",
    "text",
    "stack",
    "group",
    "polar",
    "pie",
    "radialArc",
    "sankeyDiagram",
    "scaleLinear",
    "scaleBand",
    "scalePoint",
    "scaleOrdinal",
    "colorLegend",
    "tooltip",
    "palette",
    "eur",
    "eurShort",
    "monthShort",
)

# Anything that could reach outside the sandbox or hang the check. The browser runtime is
# sandboxed as well, so this is about giving the model a readable rule rather than about safety.
FORBIDDEN = (
    "import",
    "require",
    "fetch",
    "window",
    "document",
    "globalThis",
    "process",
    "eval",
    "XMLHttpRequest",
    "localStorage",
    "setTimeout",
    "setInterval",
)

# Several object literals with a figure among them, in one array: rows typed into the code. A
# single object with a number in it is configuration (a gradient stop, a tooltip item), not data.
INLINE_DATA = re.compile(r"\[\s*\{[^\[\]]*?:\s*-?\d[^\[\]]*?\}\s*,\s*\{", re.DOTALL)

# The findings that are not about correctness. A chart with a legend nobody needs, or with one
# colour too many, still answers the question, so after the last repair round it is shown with a
# note instead of thrown away. Everything else is refused.
LEGEND_MISSING = (
    "More than one series needs a legend: `color: { legend: colorLegend({ placement: 'bottom' }) }`."
)
LEGEND_EXTRA = "One series needs no legend. Drop the `color.legend` option."
SERIES_CEILING = f"The palette holds {MAX_SERIES} colours"
TOO_MANY_SERIES = (
    f"{SERIES_CEILING} and this chart asks for {{count}}, so two groups would be painted the "
    f"same. Keep the {MAX_SERIES - 1} largest groups and sum the rest into one 'Other' group "
    f"before drawing, with one figure per position and group."
)
COSMETIC = frozenset({LEGEND_MISSING, LEGEND_EXTRA})


def is_cosmetic(finding: str) -> bool:
    """Whether a finding is about presentation rather than about a chart that cannot be drawn."""
    return finding in COSMETIC or finding.startswith(SERIES_CEILING)


CHECK_SECONDS = 2.0
MEMORY_LIMIT = 64 * 1024 * 1024
SAMPLE_ROWS = 3

_STUB = """
var __finquery = {};

__finquery.run = function (source, rowsJson) {
  var rows = JSON.parse(rowsJson);
  var report = {
    error: null,
    defines: 0,
    returned: false,
    dataRead: false,
    marks: [],
    spec: null,
    polar: null
  };

  var CHANNELS = ['x', 'x1', 'x2', 'y', 'y1', 'y2', 'z', 'color', 'key', 'text', 'value',
    'angle', 'radius', 'radius1', 'radius2', 'source', 'target', 'nodeKey', 'linkKey',
    'orderBy', 'r'];

  function arrayOf(value) {
    if (Array.isArray(value)) return value.slice();
    return [];
  }

  function keysOf(list) {
    var keys = [];
    for (var i = 0; i < list.length; i++) {
      var row = list[i];
      if (!row || typeof row !== 'object') continue;
      var own = Object.keys(row);
      for (var j = 0; j < own.length; j++) {
        if (keys.indexOf(own[j]) === -1) keys.push(own[j]);
      }
    }
    return keys;
  }

  function counts(list, column) {
    var filled = 0;
    var numeric = 0;
    for (var i = 0; i < list.length; i++) {
      var row = list[i];
      if (!row || typeof row !== 'object') continue;
      var value = row[column];
      if (value === null || value === undefined || value === '') continue;
      filled += 1;
      if (typeof value === 'number' && isFinite(value)) numeric += 1;
    }
    return { filled: filled, numeric: numeric };
  }

  function filledKeys(list, keys) {
    var filled = [];
    for (var i = 0; i < keys.length; i++) {
      if (counts(list, keys[i]).filled > 0) filled.push(keys[i]);
    }
    return filled;
  }

  function describeChannels(options, list) {
    var described = {};
    if (!options) return described;
    for (var i = 0; i < CHANNELS.length; i++) {
      var name = CHANNELS[i];
      if (!(name in options)) continue;
      var value = options[name];
      if (typeof value === 'string') {
        var seen = counts(list, value);
        described[name] = { type: 'string', value: value, filled: seen.filled, numeric: seen.numeric };
      } else {
        described[name] = { type: typeof value };
      }
    }
    return described;
  }

  // The series of a mark: the distinct values of its `z` or `color` channel, which may be a
  // column name or an accessor, so the accessor is called the way the real mark would call it.
  function seriesOf(list, channel) {
    if (!channel) return [];
    var seen = [];
    for (var i = 0; i < list.length; i++) {
      var row = list[i];
      if (!row || typeof row !== 'object') continue;
      var value;
      if (typeof channel === 'function') {
        try {
          value = channel(row);
        } catch (error) {
          return [];
        }
      } else {
        value = row[channel];
      }
      if (value === null || value === undefined) continue;
      if (seen.indexOf(String(value)) === -1) seen.push(String(value));
    }
    return seen;
  }

  function pick(options, names) {
    var picked = {};
    for (var i = 0; i < names.length; i++) {
      if (options && names[i] in options) picked[names[i]] = options[names[i]];
    }
    return picked;
  }

  // A stack needs one figure per position and series. The rows the query returned are judged
  // before any code runs, but code that folds groups together builds its own array, and
  // TanStack throws on the duplicates it makes ("duplicate 2025-01 / Sonstiges").
  function duplicatePairs(list, position, group) {
    if (position === undefined || position === null || group === null) return [];
    var seen = {};
    var repeated = [];
    for (var i = 0; i < list.length; i++) {
      var row = list[i];
      if (!row || typeof row !== 'object') continue;
      var at;
      var of;
      // An accessor that throws is the mark's own problem to report, not this rule's.
      try {
        at = typeof position === 'function' ? position(row) : row[position];
        of = typeof group === 'function' ? group(row) : row[group];
      } catch (error) {
        return [];
      }
      var key = String(at) + ' / ' + String(of);
      if (seen[key]) {
        if (repeated.indexOf(key) === -1) repeated.push(key);
      } else {
        seen[key] = 1;
      }
    }
    return repeated;
  }

  function record(kind, source, options) {
    var list = arrayOf(source);
    var group = null;
    if (options && options.z !== undefined) group = options.z;
    else if (options && options.color !== undefined) group = options.color;
    var position = options ? (kind === 'barX' ? options.y : options.x) : undefined;
    var keys = keysOf(list);
    report.marks.push({
      kind: kind,
      rows: list.length,
      keys: keys,
      filled: filledKeys(list, keys),
      channels: describeChannels(options, list),
      layout: options && options.layout ? options.layout.__layout : null,
      innerRadius: !!(options && options.innerRadius !== undefined),
      series: seriesOf(list, group),
      // The legend reads the `color` channel and nothing else, so its values are recorded
      // apart from the series: `z` can name the groups while `color` returns their index.
      colors: seriesOf(list, options ? options.color : null),
      duplicates: duplicatePairs(list, position, group)
    });
    return { __mark: kind };
  }

  function scaleStub(kind) {
    var stub = { __scale: kind, __domain: null };
    var methods = ['range', 'padding', 'paddingInner', 'paddingOuter', 'align',
      'round', 'rangeRound', 'clamp', 'nice', 'unknown', 'copy'];
    for (var i = 0; i < methods.length; i++) {
      stub[methods[i]] = function () { return stub; };
    }
    // The one configured option the rules care about: a domain says where the axis starts.
    stub.domain = function (values) {
      if (values !== undefined) stub.__domain = Array.isArray(values) ? values.slice() : values;
      return stub;
    };
    return stub;
  }

  function describeScale(entry) {
    if (entry === null || entry === undefined) return null;
    var kind = null;
    var domain = null;
    var scale = entry.scale;
    // A zero-argument factory is called again per layout and its domain is inferred from the
    // channels, so a domain configured inside one is thrown away. That is worth reporting.
    var factory = typeof scale === 'function';
    if (factory) {
      try {
        var made = scale();
        kind = made && made.__scale ? made.__scale : null;
        domain = made && made.__domain ? made.__domain : null;
      } catch (error) {
        kind = null;
      }
    } else if (scale && scale.__scale) {
      kind = scale.__scale;
      domain = scale.__domain;
    }
    var axis = entry.axis;
    var format = false;
    if (axis && axis !== true && axis.ticks && typeof axis.ticks.format === 'function') format = true;
    var labels = axis && axis !== true ? axis.tickLabels : undefined;
    return {
      hasScale: scale !== undefined && scale !== null,
      scale: kind,
      factory: factory,
      domain: domain,
      grid: entry.grid === true,
      axis: axis !== false,
      tickFormat: format,
      // 'off' keeps every label, 'on' lets the layout drop some, 'none' is the default, which
      // also drops some.
      thin: labels === undefined || labels === null || labels.thin === undefined
        ? 'none'
        : (labels.thin === false ? 'off' : 'on'),
      rotate: labels && typeof labels.rotate === 'number' ? labels.rotate : null
    };
  }

  var globals = {};

  globals.defineChart = function (spec, options) {
    report.defines += 1;
    var merged = {};
    var base = spec && spec.__definition ? spec.__spec : spec;
    if (base && typeof base === 'object') {
      var keys = Object.keys(base);
      for (var i = 0; i < keys.length; i++) merged[keys[i]] = base[keys[i]];
    }
    if (options && typeof options === 'object') {
      var extra = Object.keys(options);
      for (var j = 0; j < extra.length; j++) merged[extra[j]] = options[extra[j]];
    }
    return { __definition: true, __spec: merged };
  };

  globals.lineY = function (source, options) { return record('lineY', source, options); };
  globals.areaY = function (source, options) { return record('areaY', source, options); };
  globals.barY = function (source, options) { return record('barY', source, options); };
  globals.barX = function (source, options) { return record('barX', source, options); };
  globals.link = function (source, options) { return record('link', source, options); };
  globals.rect = function (source, options) { return record('rect', source, options); };
  globals.text = function (source, options) { return record('text', source, options); };
  globals.radialArc = function (source, options) { return record('radialArc', source, options); };

  globals.stack = function (options) { return { __layout: 'stack', options: options || {} }; };
  globals.group = function (options) { return { __layout: 'group', options: options || {} }; };

  globals.polar = function (options) {
    if (!options || !Array.isArray(options.marks) || options.marks.length === 0) {
      throw new Error('polar needs a marks array');
    }
    report.polar = {
      scaleKeys: options.scales ? Object.keys(options.scales) : [],
      marks: options.marks.length
    };
    return { __mark: 'polar' };
  };

  globals.pie = function (source, options) {
    var list = arrayOf(source);
    if (!options || options.value === undefined) throw new Error('pie needs a value channel');
    var read = function (row) {
      return typeof options.value === 'function' ? options.value(row) : row[options.value];
    };
    var total = 0;
    for (var i = 0; i < list.length; i++) {
      var value = read(list[i]);
      if (typeof value !== 'number' || !isFinite(value)) {
        throw new Error('pie needs a finite number in "' + options.value + '", got ' +
          JSON.stringify(value));
      }
      if (value < 0) throw new Error('pie cannot allocate the negative value ' + value);
      total += value;
    }
    var slices = [];
    var used = 0;
    for (var j = 0; j < list.length; j++) {
      var row = list[j];
      var slice = {};
      var keys = Object.keys(row);
      for (var k = 0; k < keys.length; k++) slice[keys[k]] = row[keys[k]];
      var share = total > 0 ? read(row) / total : 0;
      slice.value = read(row);
      slice.index = j;
      slice.fraction = share;
      slice.startAngle = used;
      slice.endAngle = used + share * 6.283185307179586;
      slice.angle = (slice.startAngle + slice.endAngle) / 2;
      slice.padAngle = 0;
      slice.source = row;
      slice.sourceIndexes = [j];
      used = slice.endAngle;
      slices.push(slice);
    }
    return slices;
  };

  globals.sankeyDiagram = function (options) {
    if (!options) throw new Error('sankeyDiagram needs options');
    var nodeRows = arrayOf(options.nodes);
    var linkRows = arrayOf(options.links);
    if (nodeRows.length === 0) throw new Error('sankeyDiagram got no nodes');
    if (linkRows.length === 0) throw new Error('sankeyDiagram got no links');
    var read = function (row, accessor) {
      return typeof accessor === 'function' ? accessor(row) : row[accessor];
    };
    var keys = [];
    for (var i = 0; i < nodeRows.length; i++) {
      var key = read(nodeRows[i], options.nodeKey);
      if (key === undefined || key === null || key === '') {
        throw new Error('a node row has no nodeKey value');
      }
      if (keys.indexOf(String(key)) !== -1) {
        throw new Error('the node "' + key + '" appears twice; node keys must be unique');
      }
      keys.push(String(key));
    }
    var nodes = [];
    for (var n = 0; n < nodeRows.length; n++) {
      nodes.push({
        kind: 'node', key: keys[n], index: n, depth: 0, height: 0, layer: 0, value: 1,
        x0: 0, x1: 14, y0: n * 24, y1: n * 24 + 20, x: 7, y: n * 24 + 10,
        data: nodeRows[n], source: nodeRows[n], sourceIndexes: [n],
        incomingLinks: [], outgoingLinks: []
      });
    }
    var links = [];
    for (var l = 0; l < linkRows.length; l++) {
      var row = linkRows[l];
      var from = read(row, options.source);
      var to = read(row, options.target);
      if (keys.indexOf(String(from)) === -1) {
        throw new Error('a link starts at the unknown node "' + from +
          '"; the nodes array must hold every source and target');
      }
      if (keys.indexOf(String(to)) === -1) {
        throw new Error('a link ends at the unknown node "' + to +
          '"; the nodes array must hold every source and target');
      }
      var value = read(row, options.value);
      if (typeof value !== 'number' || !isFinite(value)) {
        throw new Error('the link value must be a finite number, got ' + JSON.stringify(value));
      }
      if (value <= 0) throw new Error('a link value must be a positive amount, got ' + value);
      if (String(from) === String(to)) {
        throw new Error('the link "' + from + '" flows into itself; a flow needs two names');
      }
      links.push({
        kind: 'link', key: l, data: row, source: row, sourceRows: [row], sourceIndexes: [l],
        sourceKey: String(from), targetKey: String(to),
        sourceNode: nodes[keys.indexOf(String(from))],
        targetNode: nodes[keys.indexOf(String(to))],
        value: value, width: 6, x1: 14, y1: 20, x2: 200, y2: 60
      });
    }
    record('sankeyDiagram', linkRows, pick(options, ['source', 'target', 'value', 'linkKey']));
    record('sankey_nodes', nodeRows, pick(options, ['nodeKey']));
    // A cycle is what the layout reports as "circular link" in the browser, so it is refused
    // here with the names on it instead.
    var outgoing = {};
    for (var c = 0; c < links.length; c++) {
      if (!outgoing[links[c].sourceKey]) outgoing[links[c].sourceKey] = [];
      outgoing[links[c].sourceKey].push(links[c].targetKey);
    }
    var state = {};
    var trail = [];
    var walk = function (node) {
      state[node] = 1;
      trail.push(node);
      var next = outgoing[node] || [];
      for (var w = 0; w < next.length; w++) {
        if (state[next[w]] === 1) return trail.slice(trail.indexOf(next[w])).concat([next[w]]);
        if (!state[next[w]]) {
          var found = walk(next[w]);
          if (found) return found;
        }
      }
      state[node] = 2;
      trail.pop();
      return null;
    };
    for (var k = 0; k < keys.length; k++) {
      if (state[keys[k]]) continue;
      var cycle = walk(keys[k]);
      if (cycle) {
        throw new Error('the links form the circular flow ' + cycle.join(' -> ') +
          '; a sankey cannot lay that out');
      }
    }
    if (typeof options.marks !== 'function') {
      throw new Error('sankeyDiagram needs a marks function returning the child marks');
    }
    var children = options.marks({
      id: 'sankey',
      chart: { x: 0, y: 0, width: 640, height: 280 },
      nodes: nodes,
      links: links
    });
    if (!Array.isArray(children) || children.length === 0) {
      throw new Error('the sankey marks function must return at least one mark');
    }
    return { __mark: 'sankeyDiagram' };
  };

  globals.scaleLinear = function () { return scaleStub('linear'); };
  globals.scaleBand = function () { return scaleStub('band'); };
  globals.scalePoint = function () { return scaleStub('point'); };
  globals.scaleOrdinal = function () { return scaleStub('ordinal'); };
  globals.colorLegend = function (options) { return { __legend: true, options: options || {} }; };
  globals.tooltip = { __tooltip: true };
  globals.palette = ['#0f766e', '#4f46e5', '#b45309', '#7c3aed', '#be123c', '#0369a1'];
  globals.eur = function (value) { return String(value) + ' EUR'; };
  globals.eurShort = function (value) { return String(value) + ' EUR'; };
  globals.monthShort = function (value) { return String(value).slice(0, 3); };

  var names = [__GLOBAL_NAMES__];
  var values = [];
  for (var g = 0; g < names.length; g++) values.push(globals[names[g]]);

  var view = new Proxy(rows, {
    get: function (target, property) {
      report.dataRead = true;
      return target[property];
    }
  });

  var made;
  try {
    made = Function.apply(null, ['data'].concat(names).concat([source]));
  } catch (error) {
    report.error = 'The code does not compile: ' + error.name + ': ' + error.message;
    return JSON.stringify(report);
  }

  var returned;
  try {
    returned = made.apply(null, [view].concat(values));
  } catch (error) {
    report.error = 'The code threw ' + error.name + ': ' + error.message;
    return JSON.stringify(report);
  }

  report.returned = !!(returned && returned.__definition === true);
  if (report.returned) {
    var spec = returned.__spec || {};
    var scales = spec.scales;
    report.spec = {
      keys: Object.keys(spec),
      hasScales: !!scales,
      xPresent: !!scales && 'x' in scales,
      yPresent: !!scales && 'y' in scales,
      x: scales ? describeScale(scales.x) : null,
      y: scales ? describeScale(scales.y) : null,
      tooltip: !!spec.tooltip,
      legend: !!(spec.color && spec.color.legend),
      guides: spec.guides === undefined ? null : spec.guides,
      markCount: Array.isArray(spec.marks) ? spec.marks.length : 0
    };
  }
  return JSON.stringify(report);
};
"""


def _stub_source() -> str:
    return _STUB.replace("__GLOBAL_NAMES__", ", ".join(f"'{name}'" for name in GLOBAL_NAMES))


@dataclass(frozen=True)
class CheckResult:
    """What the self-check found. No findings means the chart may be shown."""

    findings: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.findings

    @property
    def fatal(self) -> bool:
        """True when a finding is about more than polish, so the chart must not be shown."""
        return any(not is_cosmetic(finding) for finding in self.findings)

    def instructions(self) -> str:
        return "\n".join(f"- {finding}" for finding in self.findings)


def _static_findings(code: str) -> list[str]:
    findings: list[str] = []
    if not code.strip():
        findings.append("The code is empty. Write the function body.")
        return findings
    for token in FORBIDDEN:
        if re.search(rf"\b{re.escape(token)}\b", code):
            findings.append(
                f"`{token}` may not be used. The code runs in a sandbox with only the listed "
                f"globals, no imports and no browser APIs."
            )
    if INLINE_DATA.search(code):
        findings.append(
            "The numbers are typed into the code. Every value must be read from `data` through "
            "a channel such as `y: 'total_eur'`; never write an array of rows yourself."
        )
    return findings


def _looks_like_a_period(rows: list[dict[str, Any]], column: str) -> bool:
    """Whether a column holds ordered periods (2025-01 or 2025-01-17) rather than names.

    The two rules that follow from it pull in opposite directions: a period axis is formatted
    with `monthShort` and may drop labels, because a reader reads the missing ones off their
    neighbours; a name axis may not drop a single one.
    """
    values = [row.get(column) for row in rows if row.get(column) is not None]
    return bool(values) and all(
        re.fullmatch(r"\d{4}-\d{2}(-\d{2})?", str(value)) for value in values
    )


def _run_in_quickjs(code: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    context = quickjs.Context()
    context.set_memory_limit(MEMORY_LIMIT)
    context.set_time_limit(CHECK_SECONDS)
    context.eval(_stub_source())
    report = context.eval(f"__finquery.run({json.dumps(code)}, {json.dumps(json.dumps(rows))})")
    parsed = json.loads(str(report))
    assert isinstance(parsed, dict)
    return parsed


# The channel that carries euros, per mark. It has to hold finite numbers or nothing is drawn.
VALUE_CHANNEL = {
    "lineY": "y",
    "areaY": "y",
    "barY": "y",
    "barX": "x",
    "sankeyDiagram": "value",
}


def _mark_findings(report: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    for mark in report["marks"]:
        kind = mark["kind"]
        keys = mark["keys"]
        if mark["rows"] == 0:
            findings.append(
                f"`{kind}` was given an empty array, so it would draw nothing. Pass the rows it "
                f"should draw."
            )
            continue
        for channel, described in mark["channels"].items():
            if described["type"] != "string":
                continue
            column = described["value"]
            if column not in keys:
                findings.append(
                    f'`{kind}` reads the column "{column}" in its `{channel}` channel, which does '
                    f"not exist. The columns are: {', '.join(keys)}."
                )
            elif described["filled"] == 0:
                usable = ", ".join(mark["filled"]) or "none of them"
                findings.append(
                    f'`{kind}` reads the column "{column}" in its `{channel}` channel, but that '
                    f"column is empty in every row, so nothing would be drawn. The columns that "
                    f"carry values: {usable}."
                )
            elif channel == VALUE_CHANNEL.get(kind) and described["numeric"] == 0:
                findings.append(
                    f'`{kind}` reads the column "{column}" as its figure, but that column holds '
                    f"no numbers. The euro column is the one with numbers in it."
                )
    return findings


def _series_count(report: dict[str, Any]) -> int:
    """How many colours the chart actually asks for, over every mark."""
    return max((len(mark["series"]) for mark in report["marks"]), default=0)


# A legend label that is a bare number is a colour assigned by rank instead of by name.
A_NUMBER = re.compile(r"-?\d+(\.\d+)?")


def _numeric_colours(report: dict[str, Any]) -> list[str]:
    """The colour values of a mark that colours by index rather than by the group's name."""
    for mark in report["marks"]:
        values = mark["colors"]
        if len(values) > 1 and all(A_NUMBER.fullmatch(value) for value in values):
            return values
    return []


def _duplicate_pairs(report: dict[str, Any], kinds: tuple[str, ...]) -> list[str]:
    """The (position, group) pairs a data mark was handed more than once, over the marks drawn."""
    repeated: list[str] = []
    for mark in report["marks"]:
        if mark["kind"] not in kinds:
            continue
        for pair in mark["duplicates"]:
            if pair not in repeated:
                repeated.append(pair)
    return repeated


def _value_columns(report: dict[str, Any]) -> list[str]:
    """The distinct columns the data marks read as their figure, in the order they were drawn."""
    seen: list[str] = []
    for mark in report["marks"]:
        channel = VALUE_CHANNEL.get(mark["kind"])
        described = mark["channels"].get(channel) if channel else None
        if described and described["type"] == "string" and described["value"] not in seen:
            seen.append(described["value"])
    return seen


def _shape_findings(report: dict[str, Any], shape: Shape) -> list[str]:
    rule = SHAPES[shape]
    kinds = {mark["kind"] for mark in report["marks"]}
    findings: list[str] = []
    for required in rule.required:
        if required not in kinds:
            findings.append(f"The plan asks for {shape}, so `{required}` has to be the mark.")
    for family in FAMILY_MARKS:
        if family in kinds and family not in rule.required and family not in rule.also_allowed:
            findings.append(f"`{family}` does not belong in a {shape} chart. Remove that mark.")
    if shape == "doughnut":
        arcs = [mark for mark in report["marks"] if mark["kind"] == "radialArc"]
        for arc in arcs:
            if arc["rows"] > MAX_SLICES:
                findings.append(
                    f"A doughnut shows at most {MAX_SLICES} slices and this one has "
                    f"{arc['rows']}. Keep the largest {MAX_SLICES - 1} and add the rest as "
                    f'"Other", or pick the bar shape instead.'
                )
            if not arc["innerRadius"]:
                findings.append("A doughnut needs `innerRadius` on `radialArc`, or it is a pie.")
        if report["polar"] is None:
            findings.append("`radialArc` only works inside `polar({ ... })`.")
        elif sorted(report["polar"]["scaleKeys"]) != ["angle", "radius"]:
            findings.append(
                "`polar` needs both `scales.angle` and `scales.radius`; use `null` for each "
                "when the arcs carry their own geometry."
            )
    series = _series_count(report)
    if rule.series and series < 2:
        channels = "`z` and `color`" if rule.crossed else "`color`"
        findings.append(
            f"A {shape} chart separates its data by colour, so the mark needs {channels} "
            f"pointing at the column that names the groups."
        )
    if rule.crossed and series > MAX_SERIES:
        findings.append(TOO_MANY_SERIES.format(count=series))
    # The rows a query returned are judged before the code pass, but code that folds groups
    # together builds its own array, and a fold that relabels without summing makes exactly the
    # duplicates TanStack throws on in the browser (review of 2026-09-05).
    if rule.crossed and (repeated := _duplicate_pairs(report, rule.required)):
        shown = ", ".join(repeated[:3])
        pairs = "one pair" if len(repeated) == 1 else f"{len(repeated)} pairs"
        findings.append(
            f"The rows this mark was given carry {pairs} of position and group more than once "
            f"({shown}), and a stack needs one figure per pair. Folding groups means summing "
            f"their figures, not relabelling their rows."
        )
    # `color: (row) => topics.indexOf(row.topic)` draws the right bars and labels the legend
    # "0" and "1" (review of 2026-09-05). Colour follows the entity, never its rank.
    if numbered := _numeric_colours(report):
        findings.append(
            f"The legend would read {', '.join(numbered)}, because the `color` channel gives "
            f"back a number instead of a name. Colour by the group itself, `color: 'topic'` or "
            f"`color: (row) => short(row.topic)`, so the legend names the categories."
        )
    # Two marks over two euro columns and no series between them stack into a total nobody
    # asked for: income drawn on top of spending was one of them (review of 2026-09-05).
    if not rule.series and len(drawn := _value_columns(report)) > 1:
        findings.append(
            f"Two marks draw different euro columns ({', '.join(drawn)}) with nothing to tell "
            f"them apart, so they stack into a total nobody asked for. A {shape} chart draws one "
            f"figure per position: draw the column the request is about, and leave the other out."
        )
    layouts = {mark["layout"] for mark in report["marks"] if mark["kind"] in rule.required}
    if rule.grouped and "group" not in layouts:
        findings.append("Grouped bars need `layout: group()`, otherwise they stack.")
    if shape == "bar_stacked" and "group" in layouts:
        findings.append("Stacked bars must not use `layout: group()`.")
    return findings


def _domain_findings(axis: dict[str, Any], name: str, *, owns: str) -> list[str]:
    """Who owns this axis' domain, and does it still hold zero.

    The library reads one thing off the `scale` entry before anything else: a bare factory
    (`scaleLinear`) means "infer the domain from the marks", a configured scale
    (`scaleLinear()`) means "this domain is mine, leave it alone". Both mistakes that follow
    from that are silent and total. A domain written inside `() => scaleLinear().domain(...)`
    is inferred over again and thrown away; a `scaleLinear()` with no domain keeps the scale's
    own default of 0 to 1, so every bar fills the plot and the axis reads "0 EUR ... 1 EUR",
    which is what the top-merchant chart did on 2026-09-05.

    Then the euro axis has to include zero. A bar and an area rest on it by themselves, because
    the mark contributes its baseline to the inferred domain; a line does not, which is how a
    range of 4.401 to 5.522 EUR came to fill a whole card in the review of 2026-09-04.
    """
    domain, factory = axis["domain"], axis["factory"]
    if factory and domain is not None:
        return [
            f"`scales.{name}` configures a domain inside a zero-argument factory, and the chart "
            f"infers the domain again from the data, so yours is thrown away. Pass the scale "
            f"itself: `scale: scaleLinear().domain([...])`, without the `() =>`."
        ]
    if not factory and domain is None:
        fix = (
            "give it `.domain([Math.min(0, ...amounts), Math.max(0, ...amounts)])`"
            if owns == "required"
            else "pass the factory itself (`scaleLinear`, `scaleBand` or `scalePoint`, without "
            "the brackets) and let the chart infer it"
        )
        return [
            f"`scales.{name}` is a configured scale with no domain, so it keeps the scale's own "
            f"default of 0 to 1 and every mark fills the plot. Either {fix}."
        ]
    if domain is not None and owns == "refused":
        return [
            f"This mark rests on zero by itself and the chart works out how high to go, so "
            f"`scales.{name}` takes the bare factory `scale: scaleLinear` and names no domain. "
            f"A domain over the row values caps the axis below a stack's own total."
        ]
    if domain is None:
        if owns != "required":
            return []
        return [
            f"The euro axis has to start at zero, or a change of a few percent is drawn as a "
            f"cliff. Give `scales.{name}` the domain "
            f"`scale: scaleLinear().domain([Math.min(0, ...amounts), Math.max(0, ...amounts)])` "
            f"over the figures the chart draws."
        ]
    numbers = [
        value for value in domain if isinstance(value, (int, float)) and not isinstance(value, bool)
    ]
    if len(numbers) == 2 and not numbers[0] <= 0 <= numbers[1]:
        return [
            f"`scales.{name}` was given the domain {numbers}, which cuts the zero baseline off. "
            f"A euro axis includes zero: "
            f"`.domain([Math.min(0, ...amounts), Math.max(0, ...amounts)])`."
        ]
    return []


def _house_findings(report: dict[str, Any], shape: Shape, rows: list[dict[str, Any]]) -> list[str]:
    rule = SHAPES[shape]
    spec = report["spec"]
    findings: list[str] = []
    owned = [key for key in ("height", "width", "title") if key in spec["keys"]]
    if owned:
        findings.append(
            f"The card owns the size and the caption, so drop {', '.join(owned)} from the "
            f"definition."
        )
    if not spec["tooltip"]:
        findings.append("Every chart carries `tooltip: { use: tooltip, format: ... }`.")
    if not spec["hasScales"] or not spec["xPresent"] or not spec["yPresent"]:
        findings.append(
            "`scales` must always declare both `x` and `y`; use `null` for an axis the shape "
            "does not use."
        )
        return findings

    if rule.value_axis is not None:
        value = spec[rule.value_axis]
        if value is None or not value["hasScale"]:
            findings.append(f"`scales.{rule.value_axis}` needs the euro scale (`scaleLinear`).")
        else:
            if value["scale"] != "linear":
                findings.append(f"`scales.{rule.value_axis}` must use `scaleLinear` for euros.")
            if not value["grid"]:
                findings.append(f"Set `grid: true` on `scales.{rule.value_axis}`, the euro axis.")
            if not value["tickFormat"]:
                findings.append(
                    f"The euro axis needs `axis: {{ ticks: {{ format: eurShort }} }}` on "
                    f"`scales.{rule.value_axis}`."
                )
            findings.extend(
                _domain_findings(
                    value,
                    rule.value_axis,
                    owns="refused" if rule.zero_from_mark else "required",
                )
            )
    if rule.category_axis is not None:
        category = spec[rule.category_axis]
        if category is None or not category["hasScale"]:
            findings.append(
                f"`scales.{rule.category_axis}` needs the category scale (`scaleBand` for bars, "
                f"`scalePoint` for lines and areas)."
            )
        else:
            if category["grid"]:
                findings.append(
                    f"Only the euro axis carries a grid. Remove `grid` from "
                    f"`scales.{rule.category_axis}`."
                )
            findings.extend(_domain_findings(category, rule.category_axis, owns="free"))
            columns = [
                mark["channels"][rule.category_axis]["value"]
                for mark in report["marks"]
                if mark["channels"].get(rule.category_axis, {}).get("type") == "string"
            ]
            periods = any(_looks_like_a_period(rows, column) for column in columns)
            if periods and not category["tickFormat"]:
                findings.append(
                    f"The values read as periods (2025-01, 2025-03-14), so "
                    f"`scales.{rule.category_axis}` needs "
                    f"`axis: {{ ticks: {{ format: monthShort }} }}`."
                )
            # A month can be read off its neighbours, a category name cannot: a bar whose label
            # the layout dropped stands under blank space (review of 2026-09-04, ten bars and
            # eight labels).
            if not periods and columns and category["thin"] != "off":
                turn = (
                    ""
                    if rule.category_axis == "y"
                    else " Add `rotate: -28` beside it once there are more than six names or one "
                    "of them is long, so they do not overlap."
                )
                findings.append(
                    f"Every bar is named by its own label and none may be dropped, so "
                    f"`scales.{rule.category_axis}` needs "
                    f"`axis: {{ tickLabels: {{ thin: false }} }}`.{turn}"
                )
    # A sankey names its nodes with text marks, so it carries no colour series and no legend.
    if shape != "sankey":
        series = _series_count(report)
        if series > 1 and not spec["legend"]:
            findings.append(LEGEND_MISSING)
        # When the shape itself is asking for series, that finding is the actionable one.
        if series < 2 and spec["legend"] and not rule.series:
            findings.append(LEGEND_EXTRA)
    return findings


def _pair_findings(columns: list[str], rows: list[dict[str, Any]]) -> list[str]:
    """A stacked or grouped bar needs one figure per position and series.

    TanStack Charts throws "A stack requires at most one value for each position and series" in
    the browser, which the review of 2026-09-04 saw twice. The rows are what decide it, so this
    is judged on them and not on the code: two rows for 2025-01 / Groceries cannot be drawn by
    any definition, however well written.
    """
    if len(columns) < 2:
        return []
    position, series = columns[0], columns[1]
    seen: dict[tuple[str, str], int] = {}
    for row in rows:
        key = (str(row.get(position)), str(row.get(series)))
        seen[key] = seen.get(key, 0) + 1
    repeated = [key for key, count in seen.items() if count > 1]
    if not repeated:
        return []
    shown = ", ".join(f"{first} / {second}" for first, second in repeated[:3])
    pairs = "one pair" if len(repeated) == 1 else f"{len(repeated)} pairs"
    return [
        f"The rows carry {pairs} of {position} and {series} more than once ({shown}), and "
        f"stacked or grouped bars need one figure per pair. The query has to group by both "
        f"columns and return each combination once."
    ]


def _position_findings(columns: list[str], rows: list[dict[str, Any]]) -> list[str]:
    """One bar, or one point, per name: the first column has to name each position once.

    A CASE that always falls through to its ELSE returns seven rows all called 'Sonstiges', and
    seven bars stacked on one band is not a bar chart (review of 2026-09-05). The rows decide
    it, so no repair round could fix it.
    """
    if not columns or len(rows) < 2:
        return []
    position = columns[0]
    values = [str(row.get(position)) for row in rows]
    repeated = [value for value in dict.fromkeys(values) if values.count(value) > 1]
    if not repeated:
        return []
    shown = ", ".join(repeated[:3])
    names = "one name" if len(repeated) == 1 else f"{len(repeated)} names"
    return [
        f"The {len(rows)} rows carry only {len(set(values))} different values in {position}, "
        f"because {names} come back more than once ({shown}). One bar per name: the query has "
        f"to group by {position} and return each value once."
    ]


def _flow_findings(columns: list[str], rows: list[dict[str, Any]]) -> list[str]:
    """A sankey draws a flow, so its links must go somewhere and must not come back.

    The layout throws "circular link" on a cycle and refuses a value it cannot allocate. Both
    are properties of the rows, so both are decided here rather than in the browser.
    """
    if len(columns) < 3:
        # A UNION that forgets to select the source is a link with one end, and no definition
        # can draw that, so it is refused here instead of costing three code passes.
        return [
            f"A flow needs three columns, a source name, a target name and a positive euro "
            f"amount, and the query returned {len(columns)}: {', '.join(columns) or 'none'}. "
            f"Every row has to name both ends of its link."
        ]
    source, target, amount = columns[0], columns[1], columns[2]
    findings: list[str] = []
    edges: dict[str, list[str]] = {}
    loops: list[str] = []
    for row in rows:
        start, end = str(row.get(source)), str(row.get(target))
        if start == end:
            loops.append(start)
        edges.setdefault(start, []).append(end)
    if loops:
        flowing = "One row flows" if len(loops) == 1 else f"{len(loops)} rows flow"
        findings.append(
            f"{flowing} from a name into itself ({', '.join(dict.fromkeys(loops))}). "
            f"A flow needs a {source} and a {target} that differ."
        )
    if cycle := _first_cycle(edges):
        findings.append(
            f"The rows form a circular flow ({' -> '.join(cycle)}), which a sankey cannot lay "
            f"out. Every euro has to travel from a source to a target and stop there."
        )
    unusable = [
        row
        for row in rows
        if not isinstance(row.get(amount), (int, float))
        or isinstance(row.get(amount), bool)
        or float(row.get(amount) or 0) <= 0
    ]
    if unusable:
        carrying = "One row carries" if len(unusable) == 1 else f"{len(unusable)} rows carry"
        findings.append(
            f"{carrying} no positive figure in {amount}. Every flow is a positive euro amount, "
            f"so spending travels as `ROUND(-SUM(amount), 2)`."
        )
    return findings


def _first_cycle(edges: dict[str, list[str]]) -> list[str] | None:
    """The first cycle a depth-first walk finds, as the names on it. None when there is none."""
    colour: dict[str, int] = {}
    path: list[str] = []

    def walk(node: str) -> list[str] | None:
        colour[node] = 1
        path.append(node)
        for next_node in edges.get(node, []):
            if colour.get(next_node) == 1:
                return path[path.index(next_node) :] + [next_node]
            if colour.get(next_node) is None and (found := walk(next_node)) is not None:
                return found
        colour[node] = 2
        path.pop()
        return None

    for node in list(edges):
        if colour.get(node) is None and (found := walk(node)) is not None:
            return found
    return None


def data_findings(shape: Shape, columns: list[str], rows: list[dict[str, Any]]) -> list[str]:
    """What the rows themselves make impossible for this shape, before any code is written.

    The code check judges intent against a stub; these two rules are about the data a definition
    would be handed, so no repair round could fix them. `run_chart` calls this once the query has
    answered and reports the finding instead of drawing something the browser would throw on.
    """
    rule = SHAPES[shape]
    if rule.crossed:
        return _pair_findings(columns, rows)
    if shape == "sankey":
        return _flow_findings(columns, rows)
    if rule.category_axis is not None:
        return _position_findings(columns, rows)
    return []


def judge(report: dict[str, Any], shape: Shape, rows: list[dict[str, Any]]) -> list[str]:
    """Turn one recording into findings. Pure, so the rules are testable without QuickJS.

    Every finding appears once, however many marks earned it: eight marks reading the same wrong
    column is one thing to fix, and the repair prompt is the model's whole instruction.
    """
    return list(dict.fromkeys(_judge(report, shape, rows)))


def _judge(report: dict[str, Any], shape: Shape, rows: list[dict[str, Any]]) -> list[str]:
    if report["error"]:
        return [report["error"]]
    findings: list[str] = []
    if report["defines"] != 1:
        findings.append(
            f"Call `defineChart` exactly once and return what it gives you; it was called "
            f"{report['defines']} times."
        )
    if not report["returned"]:
        findings.append("The function body must `return defineChart({ ... })`.")
    if not report["dataRead"]:
        columns = ", ".join(dict.fromkeys(key for row in rows for key in row)) or "none"
        findings.append(
            f"The code never reads `data`. Hand those rows to the mark itself, "
            f"`barY(data, {{ ... }})`, and read every value through a channel name. The columns "
            f"are: {columns}."
        )
    if findings:
        return findings
    findings.extend(_mark_findings(report))
    findings.extend(_shape_findings(report, shape))
    findings.extend(_house_findings(report, shape, rows))
    return findings


async def check_chart_code(code: str, rows: list[dict[str, Any]], shape: Shape) -> CheckResult:
    """Compile, run and judge one chart definition. Never raises: a crash is a finding."""
    static = _static_findings(code)
    if static:
        return CheckResult(tuple(static))
    try:
        report = await asyncio.to_thread(_run_in_quickjs, code, rows)
    except quickjs.JSException as exc:
        return CheckResult((f"The code could not be checked: {exc}",))
    except Exception as exc:  # noqa: BLE001 - a broken check is a finding, never a failed turn
        return CheckResult((f"The code could not be checked: {exc}",))
    return CheckResult(tuple(judge(report, shape, rows)))
