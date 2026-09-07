import { ChevronDownIcon } from 'lucide-react'
import { useEffect, useRef, useState, type ReactNode } from 'react'

import { Select, SelectContent, SelectItem, SelectSeparator, SelectTrigger, SelectValue } from '@/components/ui/select'
import { amountInput, formatDate, formatEur, parseAmount } from '@/lib/format'
import { cn } from '@/lib/utils'

/** A cell that saved nothing keeps what the user typed and says why, right where they typed it. */
function CellError({ message }: { message: string }) {
  return (
    <span className="block px-1.5 pt-0.5 text-2xs text-destructive leading-tight" role="alert">
      {message}
    </span>
  )
}

const reason = (failure: unknown) => (failure instanceof Error ? failure.message : 'That edit was refused.')

// The hover and focus of the shadcn Button's ghost variant, so a cell you can click looks like
// every other thing you can click.
const READ = 'flex h-7 w-full items-center rounded-md px-1.5 text-left transition-colors hover:bg-muted hover:text-foreground focus-ring'
const WRITE = 'h-7 w-full rounded-md border border-input bg-background px-1.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 aria-invalid:border-destructive'

type Save<T> = (value: T) => Promise<unknown>

/** Click to edit, Enter or blur to save, Escape to give up. One behaviour for every input cell. */
function useCellEdit<T>(save: Save<T>) {
  const [editing, setEditing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  // Escape unmounts the input, which in some browsers still fires blur. This says: not that one.
  const abandoned = useRef(false)

  const commit = async (value: T) => {
    setSaving(true)
    try {
      await save(value)
      setEditing(false)
      setError(null)
    } catch (failure) {
      setError(reason(failure))
    } finally {
      setSaving(false)
    }
  }

  return {
    editing,
    error,
    saving,
    abandoned,
    open: () => {
      abandoned.current = false
      setEditing(true)
    },
    cancel: () => {
      abandoned.current = true
      setEditing(false)
      setError(null)
    },
    refuse: setError,
    commit,
  }
}

function Editing({ children, error }: { children: ReactNode; error: string | null }) {
  return (
    <div className="min-w-0">
      {children}
      {error && <CellError message={error} />}
    </div>
  )
}

export function TextCell({
  value,
  label,
  onSave,
}: {
  value: string
  label: string
  onSave: Save<string>
}) {
  const cell = useCellEdit(onSave)

  if (!cell.editing) {
    return (
      <button className={cn(READ, 'truncate')} onClick={cell.open} title={value} type="button">
        <span className="truncate">{value}</span>
      </button>
    )
  }
  return (
    <Editing error={cell.error}>
      <input
        aria-invalid={cell.error !== null}
        aria-label={label}
        autoFocus
        className={WRITE}
        defaultValue={value}
        disabled={cell.saving}
        onBlur={(event) => {
          if (cell.abandoned.current) return
          if (event.target.value === value) return cell.cancel()
          void cell.commit(event.target.value)
        }}
        onKeyDown={(event) => {
          if (event.key === 'Enter') event.currentTarget.blur()
          if (event.key === 'Escape') cell.cancel()
        }}
        type="text"
      />
    </Editing>
  )
}

export function DateCell({ value, onSave }: { value: string; onSave: Save<string> }) {
  const cell = useCellEdit(onSave)

  if (!cell.editing) {
    return (
      <button className={cn(READ, 'tabular-nums')} onClick={cell.open} type="button">
        {formatDate(value)}
      </button>
    )
  }
  return (
    <Editing error={cell.error}>
      <input
        aria-invalid={cell.error !== null}
        aria-label="Booking date"
        autoFocus
        className={WRITE}
        defaultValue={value}
        disabled={cell.saving}
        onBlur={(event) => {
          if (cell.abandoned.current) return
          if (!event.target.value || event.target.value === value) return cell.cancel()
          void cell.commit(event.target.value)
        }}
        onKeyDown={(event) => {
          if (event.key === 'Enter') event.currentTarget.blur()
          if (event.key === 'Escape') cell.cancel()
        }}
        type="date"
      />
    </Editing>
  )
}

export function AmountCell({ cents, onSave }: { cents: number; onSave: Save<number> }) {
  const cell = useCellEdit(onSave)

  if (!cell.editing) {
    return (
      <button
        className={cn(READ, 'justify-end tabular-nums', cents > 0 && 'text-primary')}
        onClick={cell.open}
        type="button"
      >
        {formatEur(cents)}
      </button>
    )
  }
  const take = (text: string) => {
    if (text.trim() === amountInput(cents)) return cell.cancel()
    const parsed = parseAmount(text)
    if (parsed === null) return cell.refuse('An amount looks like -12,50.')
    void cell.commit(parsed)
  }
  return (
    <Editing error={cell.error}>
      <input
        aria-invalid={cell.error !== null}
        aria-label="Amount in euros"
        autoFocus
        className={cn(WRITE, 'text-right tabular-nums')}
        defaultValue={amountInput(cents)}
        disabled={cell.saving}
        onBlur={(event) => {
          if (cell.abandoned.current) return
          take(event.target.value)
        }}
        onKeyDown={(event) => {
          if (event.key === 'Enter') event.currentTarget.blur()
          if (event.key === 'Escape') cell.cancel()
        }}
        type="text"
      />
    </Editing>
  )
}

export const NONE = '__none__'

export interface Choice {
  id: string
  name: string
  group?: string
}

// Copied verbatim from the closed `SelectTrigger` of `components/ui/select.tsx`, with
// `data-size="sm"` set on the element so its size variants resolve the same way: the static
// button below has to be pixel-identical to the trigger it stands in for. Keep the two in step.
const TRIGGER =
  "flex w-fit items-center justify-between gap-1.5 rounded-lg border border-input bg-transparent py-2 pr-2 pl-2.5 text-sm whitespace-nowrap transition-colors outline-none select-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-3 aria-invalid:ring-destructive/20 data-placeholder:text-muted-foreground data-[size=default]:h-8 data-[size=sm]:h-7 data-[size=sm]:rounded-[min(var(--radius-md),10px)] *:data-[slot=select-value]:line-clamp-1 *:data-[slot=select-value]:flex *:data-[slot=select-value]:items-center *:data-[slot=select-value]:gap-1.5 dark:bg-input/30 dark:hover:bg-input/50 dark:aria-invalid:border-destructive/50 dark:aria-invalid:ring-destructive/40 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4"

/** What a picker cell adds to that trigger: a borderless control the width of its column. */
const PICKER =
  'h-7! w-full min-w-0 rounded-md border-transparent px-1.5 font-normal shadow-none hover:bg-muted dark:bg-transparent dark:hover:bg-muted'

/** A cell whose value comes from a list: category, subcategory, account. One click, one change. */
export function PickerCell({
  value,
  choices,
  placeholder,
  clearLabel,
  label,
  clearable = true,
  onSave,
}: {
  value: string | null
  choices: Choice[]
  /** What the cell shows when nothing is chosen. An absence reads as a dash, like every other
   * empty cell of this table; "None" next to real names read as a subcategory of that name
   * (review of 2026-09-04). */
  placeholder: string
  /** What the item that clears the cell says, when the placeholder is not a sentence. */
  clearLabel?: string
  label: string
  clearable?: boolean
  onSave: Save<string | null>
}) {
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  // A row has three of these cells and at most one list is ever open, but every row used to
  // mount three Radix `Select` roots. Thirty-three rows of that is what made scrolling drop
  // frames (ticket 72), so the `Select` is mounted, already open, only when the user asks for
  // it, and unmounted again when it closes.
  const [open, setOpen] = useState(false)
  const button = useRef<HTMLButtonElement>(null)
  // Radix hands focus back to its own trigger, which unmounts with the `Select`. Do it here.
  const returning = useRef(false)

  useEffect(() => {
    if (open || !returning.current) return
    returning.current = false
    button.current?.focus()
  }, [open])

  const change = async (next: string) => {
    setSaving(true)
    try {
      await onSave(next === NONE ? null : next)
      setError(null)
    } catch (failure) {
      setError(reason(failure))
    } finally {
      setSaving(false)
    }
  }

  // A narrow column clips "Friends and family" to "Friends an", and the control is the only
  // place the whole name can still be read.
  const chosen = choices.find((choice) => choice.id === value)?.name
  /* An empty cell shows the placeholder, not the label of the item that clears it: a `Select`
     whose value is the clear item would otherwise print that item's words ("None") as if they
     were a real subcategory. Both are wrapped in a span that truncates: the trigger's own value
     slot clips a long account name without an ellipsis ("Sparkasse Girok"). */
  const shown = value === null ? <span className="text-muted-foreground">{placeholder}</span> : chosen

  if (!open) {
    return (
      <div className="min-w-0">
        <button
          aria-invalid={error !== null}
          aria-label={label}
          className={cn(TRIGGER, PICKER)}
          data-size="sm"
          disabled={saving}
          onClick={() => {
            returning.current = true
            setOpen(true)
          }}
          ref={button}
          title={chosen ?? placeholder}
          type="button"
        >
          <span className="min-w-0 flex-1 truncate text-left">{shown}</span>
          <ChevronDownIcon className="pointer-events-none size-4 text-muted-foreground" />
        </button>
        {error && <CellError message={error} />}
      </div>
    )
  }

  return (
    <div className="min-w-0">
      <Select
        onOpenChange={(next) => {
          if (!next) setOpen(false)
        }}
        onValueChange={(next) => void change(next)}
        open
        value={value ?? NONE}
      >
        <SelectTrigger
          aria-invalid={error !== null}
          aria-label={label}
          className={PICKER}
          size="sm"
          title={chosen ?? placeholder}
        >
          <span className="min-w-0 flex-1 truncate text-left">
            {value === null ? (
              <span className="text-muted-foreground">{placeholder}</span>
            ) : (
              <SelectValue placeholder={placeholder} />
            )}
          </span>
        </SelectTrigger>
        {/* Anchored to the trigger, not to the chosen item: Radix's default aligns the open list
            on the trigger's value node, and an empty cell renders the placeholder in its place,
            so the list was positioned nowhere (below the viewport) and nothing could be picked
            (review of 2026-09-07). */}
        <SelectContent className="max-h-72" position="popper">
          {clearable && (
            <>
              <SelectItem value={NONE}>{clearLabel ?? placeholder}</SelectItem>
              <SelectSeparator />
            </>
          )}
          {choices.map((choice) => (
            <SelectItem key={choice.id} value={choice.id}>
              {choice.group ? `${choice.group} · ${choice.name}` : choice.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {error && <CellError message={error} />}
    </div>
  )
}
