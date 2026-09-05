import { useRef, useState, type ReactNode } from 'react'

import { Select, SelectContent, SelectItem, SelectSeparator, SelectTrigger, SelectValue } from '@/components/ui/select'
import { amountInput, formatDate, formatEur, parseAmount } from '@/lib/format'
import { cn } from '@/lib/utils'

/** A cell that saved nothing keeps what the user typed and says why, right where they typed it. */
function CellError({ message }: { message: string }) {
  return (
    <span className="block px-1.5 pt-0.5 text-[11px] text-destructive leading-tight" role="alert">
      {message}
    </span>
  )
}

const reason = (failure: unknown) => (failure instanceof Error ? failure.message : 'That edit was refused.')

const READ = 'flex h-7 w-full items-center rounded-md px-1.5 text-left transition-colors hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none'
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

  return (
    <div className="min-w-0">
      <Select disabled={saving} onValueChange={(next) => void change(next)} value={value ?? NONE}>
        <SelectTrigger
          aria-invalid={error !== null}
          aria-label={label}
          className="h-7! w-full min-w-0 rounded-md border-transparent px-1.5 font-normal shadow-none hover:bg-accent dark:bg-transparent dark:hover:bg-accent"
          size="sm"
          // A narrow column clips "Friends and family" to "Friends an", and the trigger is the
          // only place the whole name can still be read.
          title={choices.find((choice) => choice.id === value)?.name ?? placeholder}
        >
          {/* An empty cell shows the placeholder, not the label of the item that clears it:
              a `Select` whose value is the clear item would otherwise print that item's words
              ("None") as if they were a real subcategory. */}
          {value === null ? (
            <span className="truncate text-muted-foreground">{placeholder}</span>
          ) : (
            <SelectValue placeholder={placeholder} />
          )}
        </SelectTrigger>
        <SelectContent className="max-h-72">
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
