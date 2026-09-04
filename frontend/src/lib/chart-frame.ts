/**
 * The message protocol between a chart card and its sandboxed runtime frame.
 *
 * The frame hosts React and TanStack Charts and evaluates generated code, so it never gets the
 * app's origin: it is loaded with `sandbox="allow-scripts"` and everything it needs (the rows,
 * the code, the resolved theme colours) is posted in. Documented in `docs/chart-runtime.md`.
 */

export const FRAME_SOURCE = 'finquery-chart-runtime'
export const CARD_SOURCE = 'finquery-chart'
/** The built runtime page. Vite builds it as a second entry; FastAPI serves it from dist. */
export const FRAME_URL = '/chart-runtime.html'
/** Every chart is this tall. The card owns the size, never the generated code. */
export const CHART_HEIGHT = 280

/** The language the chart's words are in. The euro formats stay German whatever it says. */
export type ChartLanguage = 'de' | 'en'

export type ChartValue = string | number | boolean | null
export type ChartRow = Record<string, ChartValue>

/** Colours resolved from the app's CSS variables, so the frame follows the light and dark theme. */
export interface ChartFrameTheme {
  color: string
  muted: string
  grid: string
  surface: string
  border: string
  palette: string[]
}

export interface ChartRenderMessage {
  source: typeof CARD_SOURCE
  kind: 'render'
  title: string
  language: ChartLanguage
  code: string
  rows: ChartRow[]
  theme: ChartFrameTheme
}

/** What the frame reports: it is alive, it painted, or it could not. */
export type ChartFrameEvent = { kind: 'hello' } | { kind: 'ready' } | { kind: 'error'; message: string }

export type ChartFrameMessage = ChartFrameEvent & { source: typeof FRAME_SOURCE }

export function isFrameMessage(data: unknown): data is ChartFrameMessage {
  return (
    typeof data === 'object' && data !== null && (data as { source?: unknown }).source === FRAME_SOURCE
  )
}

export function isRenderMessage(data: unknown): data is ChartRenderMessage {
  return (
    typeof data === 'object' &&
    data !== null &&
    (data as { source?: unknown }).source === CARD_SOURCE &&
    (data as { kind?: unknown }).kind === 'render'
  )
}
