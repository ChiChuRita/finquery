import { cn } from 'cn'
import { CalendarIcon } from 'lucide-react'
import type { DateRange } from 'react-day-picker'

import { Button } from '@/components/ui/button'
import { Calendar } from '@/components/ui/calendar'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { formatDate } from '@/lib/format'

/** A calendar day read as local time. `new Date('2025-03-01')` is UTC midnight, which is the
 *  day before west of Greenwich, and the calendar would then highlight the wrong cell. */
function toDate(iso: string): Date | undefined {
  const parts = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso)
  if (!parts) return undefined
  const date = new Date(Number(parts[1]), Number(parts[2]) - 1, Number(parts[3]))
  return Number.isNaN(date.getTime()) ? undefined : date
}

const pad = (value: number) => String(value).padStart(2, '0')

const toIso = (date: Date | undefined) =>
  date ? `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` : ''

/** What the trigger reads, in the date format the rest of the UI uses. */
function rangeLabel(from: string, to: string) {
  if (from && to) return `${formatDate(from)} to ${formatDate(to)}`
  if (from) return `From ${formatDate(from)}`
  if (to) return `Until ${formatDate(to)}`
  return 'Any date'
}

/**
 * One button that opens a two month calendar in range mode.
 *
 * The range is ISO `YYYY-MM-DD` on both ends, an empty string for an open end, so callers can
 * hand their filter state straight through without a Date in sight.
 */
export function DateRangePicker({
  className,
  from,
  onChange,
  to,
}: {
  className?: string
  from: string
  onChange: (range: { from: string; to: string }) => void
  to: string
}) {
  const start = toDate(from)
  const end = toDate(to)
  const selected: DateRange | undefined = start || end ? { from: start, to: end } : undefined
  const label = rangeLabel(from, to)

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          aria-label={`Booked date range: ${label}`}
          className={cn('w-60 justify-start font-normal tabular-nums', className)}
          variant="outline"
        >
          <CalendarIcon data-icon="inline-start" />
          <span className={cn('truncate', !from && !to && 'text-muted-foreground')}>{label}</span>
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-auto">
        <Calendar
          autoFocus
          defaultMonth={start ?? end}
          mode="range"
          numberOfMonths={2}
          onSelect={(range) => onChange({ from: toIso(range?.from), to: toIso(range?.to) })}
          selected={selected}
          weekStartsOn={1}
        />
        <Button
          className="self-end"
          disabled={!from && !to}
          onClick={() => onChange({ from: '', to: '' })}
          size="sm"
          variant="ghost"
        >
          Clear dates
        </Button>
      </PopoverContent>
    </Popover>
  )
}
