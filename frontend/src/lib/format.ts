const money = new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' })
const day = new Intl.DateTimeFormat('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' })
const dayTime = new Intl.DateTimeFormat('de-DE', { dateStyle: 'medium', timeStyle: 'short' })

export const formatEur = (cents: number) => money.format(cents / 100)

/** A signed euro figure: "+73,80 €", "-73,80 €", "0,00 €". For a difference, never for a total.
 *
 * `Intl` writes the minus itself and nothing in front of a positive number, so the plus is
 * added here. The sign is what says which way a delta went without relying on its colour. */
export const formatEurDelta = (cents: number) =>
  `${cents > 0 ? '+' : ''}${money.format(cents / 100)}`

const percent = new Intl.NumberFormat('de-DE', {
  style: 'percent',
  maximumFractionDigits: 1,
  signDisplay: 'exceptZero',
})

/** A signed share, from a ratio: 0.032 becomes "+3,2 %". */
export const formatPercentDelta = (ratio: number) => percent.format(ratio)

/** What an amount cell shows while it is being edited: plain, German, no currency symbol. */
export const amountInput = (cents: number) => (cents / 100).toFixed(2).replace('.', ',')

/** Read an amount a human typed, comma or dot, and return cents. Null when it is not a number. */
export function parseAmount(text: string): number | null {
  const cleaned = text.replace(/[\s€]/g, '').replace(/\.(?=\d{3}\b)/g, '').replace(',', '.')
  if (!/^-?\d+(\.\d+)?$/.test(cleaned)) return null
  return Math.round(Number(cleaned) * 100)
}
/** German dates, and never a crash: a transcript carries strings a model wrote.
 *
 * `Intl.DateTimeFormat.format` throws a RangeError on an unparseable value, and one such value
 * inside a Question card took the whole chat page down to the error boundary. Showing the
 * string as it came is the honest fallback.
 */
const formatWith = (formatter: Intl.DateTimeFormat) => (iso: string) => {
  const value = new Date(iso)
  return Number.isNaN(value.getTime()) ? iso : formatter.format(value)
}

export const formatDate = formatWith(day)
export const formatDateTime = formatWith(dayTime)
