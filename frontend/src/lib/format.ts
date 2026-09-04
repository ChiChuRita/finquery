const money = new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' })
const day = new Intl.DateTimeFormat('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' })
const dayTime = new Intl.DateTimeFormat('de-DE', { dateStyle: 'medium', timeStyle: 'short' })

export const formatEur = (cents: number) => money.format(cents / 100)

/** What an amount cell shows while it is being edited: plain, German, no currency symbol. */
export const amountInput = (cents: number) => (cents / 100).toFixed(2).replace('.', ',')

/** Read an amount a human typed, comma or dot, and return cents. Null when it is not a number. */
export function parseAmount(text: string): number | null {
  const cleaned = text.replace(/[\s€]/g, '').replace(/\.(?=\d{3}\b)/g, '').replace(',', '.')
  if (!/^-?\d+(\.\d+)?$/.test(cleaned)) return null
  return Math.round(Number(cleaned) * 100)
}
export const formatDate = (iso: string) => day.format(new Date(iso))
export const formatDateTime = (iso: string) => dayTime.format(new Date(iso))
