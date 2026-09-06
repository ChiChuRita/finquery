import { Input } from '@/components/ui/input'

/** Two days, both optional: what the dashboard is narrowed to.
 *
 * ISO `YYYY-MM-DD`, an empty string for an open end, and one `onChange` with both days, so the
 * page never has to reason about a half-applied range.
 */
export function DateRangePicker({
  from,
  to,
  onChange,
}: {
  from: string
  to: string
  onChange: (range: { from: string; to: string }) => void
}) {
  return (
    <span className="flex items-center gap-1.5">
      <Input
        aria-label="From"
        className="h-8 w-[9.5rem] text-xs"
        onChange={(event) => onChange({ from: event.target.value, to })}
        type="date"
        value={from}
      />
      <span className="text-muted-foreground text-xs">to</span>
      <Input
        aria-label="To"
        className="h-8 w-[9.5rem] text-xs"
        onChange={(event) => onChange({ from, to: event.target.value })}
        type="date"
        value={to}
      />
    </span>
  )
}
