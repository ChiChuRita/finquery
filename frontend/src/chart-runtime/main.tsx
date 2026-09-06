/**
 * The chart runtime: a sandboxed page that hosts React and TanStack Charts.
 *
 * It receives rows, generated code and the resolved theme colours by postMessage, evaluates the
 * code against the allowlisted globals and mounts one chart. Any failure is posted back to the
 * card, which shows it inline. Nothing here reaches the app: the frame has no origin, no
 * network use and no knowledge of the API.
 *
 * The frame also owns the look the code may not set (`docs/chart-runtime.md`, "The frame"): the
 * type, the axis chrome, how finely the euro axis rounds, the tooltip's surface, the animation
 * and the doughnut's centre. A stored definition from months ago gets today's look.
 */

import '@fontsource-variable/geist'

import { Chart } from '@tanstack/charts/react'
import { Component, useState, type ReactNode } from 'react'
import { createRoot } from 'react-dom/client'

import { GLOBAL_NAMES, eur, globalValues, type RenderRecord } from '@/chart-runtime/globals'
import {
  CHART_HEIGHT,
  FRAME_SOURCE,
  isRenderMessage,
  type ChartFrameEvent,
  type ChartLanguage,
  type ChartRenderMessage,
} from '@/lib/chart-frame'

const post = (event: ChartFrameEvent) =>
  window.parent.postMessage({ source: FRAME_SOURCE, ...event }, '*')

const failed = (error: unknown) =>
  post({ kind: 'error', message: error instanceof Error ? `${error.name}: ${error.message}` : String(error) })

/** The plot's own type: axis ticks, legend items and the doughnut's centre share it. */
const TICK_FONT_SIZE = 11
/** The room the page keeps around the chart, so no label sits on the frame's edge. */
const FRAME_INSET = { top: 6, side: 12 }

/** How finely a `nice: true` euro axis rounds its end, and how many ticks it then draws.
 *
 * TanStack Charts rounds a nice axis to the tick count it will draw, one tick per 48 pixels of
 * plot height: a 300 pixel frame in a side by side pair asked for three, so 13.800 EUR became an
 * axis to 20.000 EUR, and a legend under the plot left the top gridline unlabelled. The two
 * counts are one number here, so the end stays near the data and the last gridline always has
 * its label: 0, 5.000, 10.000, 15.000 for 13.800 EUR, whatever the width and the legend. */
const NICE_STEPS = 4

type Options = Record<string, unknown>
const isOptions = (value: unknown): value is Options => typeof value === 'object' && value !== null

/** The axis chrome the dataviz method fixes: no tick stubs, no axis line, one type size.
 *
 * The code says what an axis shows (the format, the thinning, the rotation); the frame says how
 * an axis is drawn. Labels sit a little off the plot, the grid is the only line, and a label
 * keeps whatever the code set on it. */
function houseAxis(options: Options): Options {
  const axis = options.axis
  if (axis === false) return options
  const authored = isOptions(axis) ? axis : {}
  const nice = options.nice === true
  const ticks: Options | false =
    authored.ticks === false ? false : { ...(isOptions(authored.ticks) ? authored.ticks : {}), size: 0, padding: 8 }
  if (ticks && nice && !('count' in ticks || 'spacing' in ticks || 'values' in ticks)) ticks.count = NICE_STEPS
  const tickLabels =
    authored.tickLabels === false
      ? false
      : { fontSize: TICK_FONT_SIZE, ...(isOptions(authored.tickLabels) ? authored.tickLabels : {}) }
  return {
    ...options,
    ...(nice ? { nice: NICE_STEPS } : {}),
    axis: { ...authored, line: false, ticks, tickLabels },
  }
}

function houseScales(scales: unknown): unknown {
  if (!isOptions(scales)) return scales
  return Object.fromEntries(
    Object.entries(scales).map(([axis, options]) => [axis, isOptions(options) ? houseAxis(options) : options]),
  )
}

interface Point {
  color?: string
}
type Format = (point: Point, context: unknown) => string
interface TooltipRow {
  label: string
  value: string
  color?: string
}

/** The code's tooltip text as one row of the app's tooltip: a swatch, the label and the figure.
 *
 * The contract has the code write plain text through `format` ("Jul 25: 2.760,80 €"). The
 * frame turns that into the tooltip's row model so the series colour stands beside the words
 * and the figure sits right-aligned in tabular digits, the way the built-in rows do. The text
 * is split at its last ": "; a text without one is the label on its own. */
function houseTooltip(options: unknown): unknown {
  if (!isOptions(options) || typeof options.format !== 'function' || 'content' in options) return options
  const format = options.format as Format
  return {
    ...options,
    content: (points: readonly Point[], context: unknown) => ({
      rows: points.map((point): TooltipRow => {
        const text = format(point, context)
        const at = text.lastIndexOf(': ')
        const label = at === -1 ? text : text.slice(0, at)
        const value = at === -1 ? '' : text.slice(at + 2)
        return { label, value, color: point.color }
      }),
    }),
  }
}

interface Built {
  definition: unknown
  record: RenderRecord
}

/** Evaluate the generated body and let the card's theme own the colours, the size and the motion. */
function buildChart(message: ChartRenderMessage): Built {
  const record: RenderRecord = { pieTotal: null }
  const body = new Function('data', ...GLOBAL_NAMES, message.code)
  const definition = body(message.rows, ...globalValues(message.theme, message.language, record)) as Options
  if (!isOptions(definition) || !('marks' in definition)) {
    throw new Error('the code did not return a chart definition')
  }
  return {
    record,
    definition: {
      ...definition,
      scales: houseScales(definition.scales),
      tooltip: houseTooltip(definition.tooltip),
      svgAnimation: { duration: 320, easing: 'ease-out' },
      theme: {
        foreground: message.theme.color,
        muted: message.theme.muted,
        grid: message.theme.grid,
        background: 'transparent',
        palette: message.theme.palette,
      },
    },
  }
}

/** A render failure inside TanStack Charts belongs in the card, not in a blank frame. */
class Boundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  componentDidCatch(error: unknown) {
    failed(error)
  }

  render() {
    return this.state.failed ? null : this.props.children
  }
}

const TOTAL_WORD: Record<ChartLanguage, string> = { de: 'Gesamt', en: 'Total' }

/** One chart, and, when it is a doughnut, its total standing in the hole.
 *
 * The polar container is a group translated to its own centre, so the centre is read off the
 * painted SVG after every render rather than computed twice. The total is the sum of the
 * slices the code handed to `pie`, which are the query's own rows: a figure from executed
 * queries, added up. */
function Mounted({ message, built }: { message: ChartRenderMessage; built: Built }) {
  const [centre, setCentre] = useState<{ x: number; y: number } | null>(null)
  const total = built.record.pieTotal
  return (
    <div style={{ position: 'relative' }}>
      <Chart
        ariaLabel={message.title}
        definition={built.definition as never}
        height={CHART_HEIGHT - FRAME_INSET.top}
        onRender={({ svg }) => {
          if (total === null) return
          const polar = svg.querySelector<SVGGElement>('.ts-chart__polar')
          const match = /translate\(([-\d.]+)[ ,]+([-\d.]+)\)/.exec(polar?.getAttribute('transform') ?? '')
          const next = match ? { x: Number(match[1]), y: Number(match[2]) } : null
          // The same centre stays the same object, so a render that moved nothing sets nothing.
          setCentre((previous) => (previous?.x === next?.x && previous?.y === next?.y ? previous : next))
        }}
      />
      {total !== null && centre && (
        <div
          aria-hidden="true"
          style={{
            position: 'absolute',
            left: centre.x,
            top: centre.y,
            transform: 'translate(-50%, -50%)',
            textAlign: 'center',
            pointerEvents: 'none',
            lineHeight: 1.25,
          }}
        >
          <div style={{ fontSize: 14, fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>{eur(total)}</div>
          <div style={{ fontSize: TICK_FONT_SIZE, color: message.theme.muted }}>{TOTAL_WORD[message.language]}</div>
        </div>
      )}
    </div>
  )
}

function applyTheme(theme: ChartRenderMessage['theme']) {
  const root = document.documentElement
  // The frame paints its own surface rather than relying on iframe transparency, so the chart
  // sits on the card's colour in both themes and `currentColor` guides stay readable.
  root.style.background = theme.surface
  root.style.color = theme.color
  root.style.setProperty('--chart-inset-top', `${FRAME_INSET.top}px`)
  root.style.setProperty('--chart-inset-side', `${FRAME_INSET.side}px`)
  // The tooltip is the app's popover: its surface, its hairline ring, its radius, its shadow
  // and its type, with the figures in tabular digits so a column of them lines up.
  root.style.setProperty('--ts-chart-tooltip-background', theme.surface)
  root.style.setProperty('--ts-chart-tooltip-color', theme.color)
  root.style.setProperty('--ts-chart-tooltip-border', `1px solid ${theme.border}`)
  root.style.setProperty('--ts-chart-tooltip-border-radius', '0.625rem')
  root.style.setProperty('--ts-chart-tooltip-shadow', '0 4px 12px rgb(0 0 0 / 0.10), 0 1px 2px rgb(0 0 0 / 0.06)')
  root.style.setProperty('--ts-chart-tooltip-padding', '0.45rem 0.65rem')
  root.style.setProperty('--ts-chart-tooltip-font', `500 12px/1.4 'Geist Variable', system-ui, sans-serif`)
  // The focus marker's inner fill is the surface, so a focused point reads as a dot with a
  // surface ring rather than a second filled disc.
  root.style.setProperty('--ts-chart-focus-fill', theme.surface)
  root.style.setProperty('--ts-chart-crosshair-marker-fill', theme.surface)
}

const container = document.getElementById('chart')
if (!container) throw new Error('the runtime page has no #chart container')
const root = createRoot(container)

window.addEventListener('error', (event) => failed(event.error ?? event.message))
window.addEventListener('unhandledrejection', (event) => failed(event.reason))

window.addEventListener('message', (event) => {
  if (!isRenderMessage(event.data)) return
  const message = event.data
  try {
    applyTheme(message.theme)
    const built = buildChart(message)
    // Keyed by the code alone: a theme switch updates the mounted chart in place, so the marks
    // take their new colours without replaying the entrance. The animation is for the first draw.
    root.render(
      <Boundary key={message.code}>
        <Mounted built={built} message={message} />
      </Boundary>,
    )
    post({ kind: 'ready' })
  } catch (error) {
    root.render(null)
    failed(error)
  }
})

post({ kind: 'hello' })
