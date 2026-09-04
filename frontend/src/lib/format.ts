const money = new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' })
const day = new Intl.DateTimeFormat('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' })
const dayTime = new Intl.DateTimeFormat('de-DE', { dateStyle: 'medium', timeStyle: 'short' })

export const formatEur = (cents: number) => money.format(cents / 100)
export const formatDate = (iso: string) => day.format(new Date(iso))
export const formatDateTime = (iso: string) => dayTime.format(new Date(iso))
