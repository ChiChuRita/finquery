/**
 * The globals a generated chart definition may use, and nothing else.
 *
 * The chart sub-agent writes a function body against exactly these names, the Python self-check
 * (`src/finquery/chart/selfcheck.py`) records calls to stubs of the same names, and this module
 * is the real thing. The three lists must stay in step; the contract is documented in
 * `docs/chart-runtime.md`.
 */

import {
  areaY,
  barX,
  barY,
  colorLegend,
  defineChart,
  group,
  lineY,
  link,
  rect,
  stack,
  text,
} from '@tanstack/charts'
import { sankeyDiagram } from '@tanstack/charts/network/sankey'
import { pie, polar, radialArc } from '@tanstack/charts/polar'
import { scaleBand } from '@tanstack/charts/scales/band'
import { scaleLinear } from '@tanstack/charts/scales/linear'
import { scaleOrdinal } from '@tanstack/charts/scales/ordinal'
import { scalePoint } from '@tanstack/charts/scales/point'
import { tooltip } from '@tanstack/charts/tooltip'

import type { ChartFrameTheme, ChartLanguage } from '@/lib/chart-frame'

const full = new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' })
// Whole euros with the German thousands separator, so an axis reads 5.000 € and 10.000 € in
// one voice. Intl's compact notation left four-digit amounts ungrouped ("5000 €" next to
// "10.000 €", ticket 35), so it is only used from a million up, where "1,2 Mio. €" earns it.
const whole = new Intl.NumberFormat('de-DE', {
  style: 'currency',
  currency: 'EUR',
  minimumFractionDigits: 0,
  maximumFractionDigits: 2,
})
const compact = new Intl.NumberFormat('de-DE', {
  style: 'currency',
  currency: 'EUR',
  notation: 'compact',
  maximumFractionDigits: 1,
})
const COMPACT_FROM = 1_000_000
/** The month names per chart language. Money stays German everywhere; the words follow the ask. */
const MONTHS: Record<ChartLanguage, string[]> = {
  de: ['Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez'],
  en: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'],
}

const numeric = (value: unknown): number | null =>
  typeof value === 'number' && Number.isFinite(value) ? value : null

/** "1.234,56 €", for tooltips. Anything that is not a number is passed through. */
export const eur = (value: unknown) => {
  const amount = numeric(value)
  return amount === null ? String(value ?? '') : full.format(amount)
}

/** "5.000 €" for axis ticks, and "1,2 Mio. €" once the amount would not fit. */
export const eurShort = (value: unknown) => {
  const amount = numeric(value)
  if (amount === null) return String(value ?? '')
  return Math.abs(amount) >= COMPACT_FROM ? compact.format(amount) : whole.format(amount)
}

/** "Jan 25" from "2025-01", and "17. Jan" or "Jan 17" from "2025-01-17", per the language.
 *
 * There is no time scale, so a month and a day are both categories and both arrive as strings.
 * A day-level axis used to print the month of every point, so nineteen ticks all read
 * "2025-03" (review of 2026-09-05); the day is what tells them apart.
 */
export const monthShortFor =
  (language: ChartLanguage) =>
  (value: unknown): string => {
    const text = String(value ?? '')
    const match = /^(\d{4})-(\d{2})(?:-(\d{2}))?/.exec(text)
    if (!match) return text
    const month = MONTHS[language][Number(match[2]) - 1]
    if (!month) return text
    if (match[3] === undefined) return `${month} ${match[1].slice(2)}`
    return language === 'de' ? `${Number(match[3])}. ${month}` : `${month} ${Number(match[3])}`
  }

/** The names, in the order `buildChart` passes them into the generated function. */
export const GLOBAL_NAMES = [
  'defineChart',
  'lineY',
  'areaY',
  'barY',
  'barX',
  'link',
  'rect',
  'text',
  'stack',
  'group',
  'polar',
  'pie',
  'radialArc',
  'sankeyDiagram',
  'scaleLinear',
  'scaleBand',
  'scalePoint',
  'scaleOrdinal',
  'colorLegend',
  'tooltip',
  'palette',
  'eur',
  'eurShort',
  'monthShort',
] as const

/** What one render of generated code told the frame on the way, for the frame's own chrome. */
export interface RenderRecord {
  /** The sum of the slices a `pie` allocated, so a doughnut can carry its total in the hole. */
  pieTotal: number | null
}

type Options = Record<string, unknown> | undefined
type Mark<T> = (rows: Iterable<T>, options?: never) => unknown

/** The house defaults a mark gets when the code did not say otherwise.
 *
 * The code keeps its own words (`barY(data, { x, y })` is still what it writes and what the
 * self-check records); the frame fills in what the dataviz method fixes across every chart, so
 * a stored definition looks the same as a freshly generated one.
 */
const withDefaults = <T,>(mark: Mark<T>, defaults: (options: Options) => Options) =>
  ((rows: Iterable<T>, options?: Options) => mark(rows, defaults(options) as never)) as unknown as Mark<T>

const hasSeries = (options: Options) => options !== undefined && ('z' in options || 'color' in options)

// The 2px surface gap of the dataviz method: touching marks are told apart by a hairline of the
// surface, never by a stroke of their own. Stacked and grouped bars get one, a doughnut's slices
// get one, a lone bar stays as it is.
const seriesGap = (surface: string) => (options: Options) =>
  hasSeries(options) ? { stroke: surface, strokeWidth: 1, ...options } : options
const sliceGap = (surface: string) => (options: Options) => ({ stroke: surface, strokeWidth: 2, ...options })

/** `pie`, recording the total of what it allocated. */
const recordingPie =
  (record: RenderRecord) =>
  <T extends object>(rows: Iterable<T>, options: Parameters<typeof pie<T>>[1]) => {
    const slices = pie(rows, options)
    record.pieTotal = slices.reduce((sum, slice) => sum + (Number.isFinite(slice.value) ? slice.value : 0), 0)
    return slices
  }

/** Everything that is the same for every render. */
const SHARED: Record<string, unknown> = {
  defineChart,
  lineY,
  areaY,
  link,
  rect,
  text,
  stack,
  group,
  polar,
  sankeyDiagram,
  scaleLinear,
  scaleBand,
  scalePoint,
  scaleOrdinal,
  colorLegend,
  tooltip,
  eur,
  eurShort,
}

/** The globals for one render: the theme's palette and surface, the language, and a record. */
export const globalValues = (theme: ChartFrameTheme, language: ChartLanguage, record: RenderRecord): unknown[] => {
  const perRender: Record<string, unknown> = {
    palette: theme.palette,
    monthShort: monthShortFor(language),
    barY: withDefaults(barY, seriesGap(theme.surface)),
    barX: withDefaults(barX, seriesGap(theme.surface)),
    radialArc: withDefaults(radialArc, sliceGap(theme.surface)),
    pie: recordingPie(record),
  }
  return GLOBAL_NAMES.map((name) => (name in perRender ? perRender[name] : SHARED[name]))
}
