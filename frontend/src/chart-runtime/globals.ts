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

import type { ChartLanguage } from '@/lib/chart-frame'

const full = new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' })
const compact = new Intl.NumberFormat('de-DE', {
  style: 'currency',
  currency: 'EUR',
  notation: 'compact',
  maximumFractionDigits: 1,
})
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

/** "1,2 Tsd. €", for axis ticks where space is short. */
export const eurShort = (value: unknown) => {
  const amount = numeric(value)
  return amount === null ? String(value ?? '') : compact.format(amount)
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

/** Everything but `palette` and `monthShort`, which arrive with each render. */
const SHARED: Record<string, unknown> = {
  defineChart,
  lineY,
  areaY,
  barY,
  barX,
  link,
  rect,
  text,
  stack,
  group,
  polar,
  pie,
  radialArc,
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

export const globalValues = (palette: readonly string[], language: ChartLanguage): unknown[] => {
  const monthShort = monthShortFor(language)
  return GLOBAL_NAMES.map((name) =>
    name === 'palette' ? palette : name === 'monthShort' ? monthShort : SHARED[name],
  )
}
