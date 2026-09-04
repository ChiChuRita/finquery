import { CheckIcon, HelpCircleIcon, SendIcon } from 'lucide-react'
import { useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import type { AskAnswer, AskOption, AskRow, AskUserInput, AskUserOutput, AskUserPart } from '@/lib/api'
import { formatDate, formatEur } from '@/lib/format'
import { cn } from '@/lib/utils'

// A card that is still open: the run is parked on this call until the user answers, which is
// exactly what `input-available` means. A reload of an unanswered card arrives as
// `approval-requested`, the state the Vercel adapter dumps a pending call as.
const OPEN = new Set(['input-available', 'approval-requested'])

type Choice = { value?: string; text?: string }

type WrappedInput = AskUserInput & { card?: WrappedInput }

/** The card's own fields, even when the model passed the whole object under a `card` key.
 *
 * A tool that hands the assistant a ready card returns it as `card`, and the assistant is told
 * to pass its fields as the arguments. The fast model sometimes passes the object instead, one
 * or two levels deep, which would render a title-less card with no rows. The server unwraps the
 * same way before it applies the answers (`finquery.ask_user.unwrap_card`).
 */
function unwrap(input: WrappedInput | undefined): AskUserInput | undefined {
  let current = input
  for (let depth = 0; depth < 3 && current?.card; depth += 1) {
    current = { ...current.card, apply: current.card.apply ?? current.apply } as WrappedInput
  }
  if (!current) return current
  return {
    ...current,
    // `"false"` is a string a model wrote, and a card that asked for no free text should not
    // grow one because of it.
    allow_free_text: String(current.allow_free_text ?? true) !== 'false',
    rows: current.rows?.map(cleanRow),
  }
}

const NULLISH = new Set(['null', 'none', 'nil', ''])

/** A model that stringifies its arguments sends `"null"` and `"430"`; read them as what they are. */
function cleanRow(row: AskRow): AskRow {
  const value = (raw: unknown) => (typeof raw === 'string' && NULLISH.has(raw.toLowerCase()) ? null : raw)
  const number = (raw: unknown) => {
    const clean = value(raw)
    return typeof clean === 'string' ? Number.parseInt(clean, 10) : (clean as number | null)
  }
  return {
    ...row,
    description: value(row.description) as string | null,
    date: value(row.date) as string | null,
    amount_cents: number(row.amount_cents),
    bookings: number(row.bookings),
  }
}

function optionsFor(row: AskRow, fallback: AskOption[]): AskOption[] {
  return row.options?.length ? row.options : fallback
}

function chosenLabel(row: AskRow, answers: AskAnswer[], fallback: AskOption[]): string | null {
  // An answer with no ref answered the question itself, so it stands for every row of it.
  const answer = answers.find((a) => a.ref === row.ref) ?? answers.find((a) => a.ref === '')
  if (!answer) return null
  if (answer.value) {
    const options = [...optionsFor(row, fallback), ...fallback]
    return options.find((o) => o.value === answer.value)?.label ?? answer.value
  }
  return answer.text ?? null
}

const sendLabel = (count: number) => {
  if (count === 0) return 'Send answers'
  return count === 1 ? 'Send 1 answer' : `Send ${count} answers`
}

function RowHeader({ row }: { row: AskRow }) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
      <div className="min-w-0">
        <p className="truncate font-medium text-sm">{row.label}</p>
        {row.description && <p className="truncate text-muted-foreground text-xs">{row.description}</p>}
      </div>
      <div className="flex shrink-0 items-center gap-2 text-xs">
        {row.bookings ? (
          <Badge variant="secondary">
            {row.bookings === 1 ? '1 booking' : `${row.bookings} bookings`}
          </Badge>
        ) : null}
        {row.date && <span className="text-muted-foreground tabular-nums">{formatDate(row.date)}</span>}
        {typeof row.amount_cents === 'number' && (
          <span className="tabular-nums">{formatEur(row.amount_cents)}</span>
        )}
      </div>
    </div>
  )
}

/** One Question card in the transcript: the rows, their buttons, a free text field per row. */
export function QuestionCard({
  part,
  onAnswer,
}: {
  part: AskUserPart
  onAnswer: (output: AskUserOutput) => void
}) {
  const [choices, setChoices] = useState<Record<string, Choice>>({})
  const [sent, setSent] = useState(false)

  // While the call is still streaming its arguments the card is half a question, so it waits.
  if (part.state === 'input-streaming') {
    return <p className="text-muted-foreground text-sm">Preparing a question...</p>
  }
  const input = unwrap(part.input as WrappedInput | undefined)
  if (!input) return null
  const rows = input.rows ?? []
  const fallback = input.options ?? []
  const answered = part.state === 'output-available' ? (part.output?.answers ?? []) : null
  // What the answers already did, written by the server, not by the model.
  const applied = part.state === 'output-available' ? part.output?.applied : null
  const open = OPEN.has(part.state) && !sent

  const answers = (): AskAnswer[] =>
    Object.entries(choices)
      .filter(([, choice]) => choice.value || choice.text?.trim())
      .map(([ref, choice]) => ({
        ref,
        value: choice.value ?? null,
        text: choice.text?.trim() ?? null,
      }))

  const send = (payload: AskAnswer[]) => {
    setSent(true)
    onAnswer({ answers: payload })
  }

  const pick = (ref: string, value: string) =>
    setChoices((previous) => ({ ...previous, [ref]: { value } }))

  const type = (ref: string, text: string) => setChoices((previous) => ({ ...previous, [ref]: { text } }))

  return (
    <div className="not-prose mb-0 w-full rounded-xl border border-primary/30 bg-primary/[0.03] p-4">
      <div className="flex items-start gap-2">
        <HelpCircleIcon aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-primary" />
        <div className="min-w-0">
          <p className="font-medium text-sm">{input.title}</p>
          {/* A mapping card writes its columns and sample rows over several lines. */}
          {input.note && <p className="mt-0.5 whitespace-pre-line text-muted-foreground text-xs">{input.note}</p>}
        </div>
      </div>

      {rows.length > 0 && (
        <ul className="mt-3 space-y-3">
          {rows.map((row) => {
            const chosen = chosenLabel(row, answered ?? [], fallback)
            const choice = choices[row.ref]
            return (
              <li className="rounded-lg border bg-card p-3" key={row.ref}>
                <RowHeader row={row} />
                {answered ? (
                  <p className="mt-2 text-xs">
                    {chosen ? (
                      <span className="inline-flex items-center gap-1.5 font-medium text-primary">
                        <CheckIcon className="size-3" />
                        {chosen}
                      </span>
                    ) : (
                      <span className="text-muted-foreground">Left for later</span>
                    )}
                  </p>
                ) : (
                  <div className="mt-2 space-y-2">
                    <div className="flex flex-wrap gap-1.5">
                      {optionsFor(row, fallback).map((option) => (
                        <Button
                          className={cn('h-7 text-xs', choice?.value === option.value && 'ring-2 ring-primary')}
                          disabled={!open}
                          key={option.value}
                          onClick={() => pick(row.ref, option.value)}
                          size="sm"
                          variant={choice?.value === option.value ? 'default' : 'outline'}
                        >
                          {option.label}
                        </Button>
                      ))}
                    </div>
                    {input.allow_free_text !== false && (
                      <Input
                        className="h-7 text-xs"
                        disabled={!open}
                        onChange={(event) => type(row.ref, event.target.value)}
                        placeholder="or type an answer"
                        value={choice?.text ?? ''}
                      />
                    )}
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      )}

      {applied && (
        <p className="mt-3 flex items-start gap-1.5 text-muted-foreground text-xs">
          <CheckIcon aria-hidden="true" className="mt-0.5 size-3 shrink-0 text-primary" />
          {applied}
        </p>
      )}

      {/* Buttons for the question itself. With no rows they are the whole answer (a mapping
          confirmation); a card that carries both is answered either way rather than having
          these silently dropped. */}
      {fallback.length > 0 && !answered && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {fallback.map((option) => (
            <Button
              className="h-7 text-xs"
              disabled={!open}
              key={option.value}
              onClick={() => send([{ ref: '', value: option.value, text: null }])}
              size="sm"
              variant="outline"
            >
              {option.label}
            </Button>
          ))}
        </div>
      )}

      {rows.length > 0 && !answered && (
        <div className="mt-3 flex items-center justify-end gap-2">
          <Button disabled={!open} onClick={() => send([])} size="sm" variant="ghost">
            Skip these
          </Button>
          <Button disabled={!open || answers().length === 0} onClick={() => send(answers())} size="sm">
            <SendIcon className="size-3.5" />
            {sendLabel(answers().length)}
          </Button>
        </div>
      )}
    </div>
  )
}
