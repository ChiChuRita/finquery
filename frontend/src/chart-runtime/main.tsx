/**
 * The chart runtime: a sandboxed page that hosts React and TanStack Charts.
 *
 * It receives rows, generated code and the resolved theme colours by postMessage, evaluates the
 * code against the allowlisted globals and mounts one chart. Any failure is posted back to the
 * card, which shows it inline. Nothing here reaches the app: the frame has no origin, no
 * network use and no knowledge of the API.
 */

import { Chart } from '@tanstack/charts/react'
import { Component, type ReactNode } from 'react'
import { createRoot } from 'react-dom/client'

import { GLOBAL_NAMES, globalValues } from '@/chart-runtime/globals'
import {
  CHART_HEIGHT,
  FRAME_SOURCE,
  isRenderMessage,
  type ChartFrameEvent,
  type ChartRenderMessage,
} from '@/lib/chart-frame'

const post = (event: ChartFrameEvent) =>
  window.parent.postMessage({ source: FRAME_SOURCE, ...event }, '*')

const failed = (error: unknown) =>
  post({ kind: 'error', message: error instanceof Error ? `${error.name}: ${error.message}` : String(error) })

/** Evaluate the generated body and let the card's theme own the colours, the size and the motion. */
function buildChart(message: ChartRenderMessage): unknown {
  const body = new Function('data', ...GLOBAL_NAMES, message.code)
  const definition = body(
    message.rows,
    ...globalValues(message.theme.palette, message.language),
  ) as Record<string, unknown>
  if (!definition || typeof definition !== 'object' || !('marks' in definition)) {
    throw new Error('the code did not return a chart definition')
  }
  return {
    ...definition,
    svgAnimation: { duration: 320, easing: 'ease-out' },
    theme: {
      foreground: message.theme.color,
      muted: message.theme.muted,
      grid: message.theme.grid,
      background: 'transparent',
      palette: message.theme.palette,
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

function applyTheme(theme: ChartRenderMessage['theme']) {
  const root = document.documentElement
  // The frame paints its own surface rather than relying on iframe transparency, so the chart
  // sits on the card's colour in both themes and `currentColor` guides stay readable.
  root.style.background = theme.surface
  root.style.color = theme.color
  root.style.setProperty('--ts-chart-tooltip-background', theme.surface)
  root.style.setProperty('--ts-chart-tooltip-color', theme.color)
  root.style.setProperty('--ts-chart-tooltip-border', `1px solid ${theme.border}`)
  root.style.setProperty('--ts-chart-tooltip-border-radius', '0.625rem')
  root.style.setProperty('--ts-chart-tooltip-shadow', '0 10px 30px rgb(0 0 0 / 0.18)')
  root.style.setProperty('--ts-chart-tooltip-font', '12px/1.4 system-ui, sans-serif')
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
    const definition = buildChart(message)
    root.render(
      <Boundary key={message.code + message.theme.color}>
        {/* The definition comes from generated code, so it carries no static type. */}
        <Chart ariaLabel={message.title} definition={definition as never} height={CHART_HEIGHT} />
      </Boundary>,
    )
    post({ kind: 'ready' })
  } catch (error) {
    root.render(null)
    failed(error)
  }
})

post({ kind: 'hello' })
