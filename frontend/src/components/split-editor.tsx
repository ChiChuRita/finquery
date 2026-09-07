import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { PlusIcon, TrashIcon } from 'lucide-react'
import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectSeparator, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Spinner } from '@/components/ui/spinner'
import { saveSplits, splitsQuery, type CategoryRef, type SplitChild, type Transaction } from '@/lib/api'
import { amountInput, formatEur, parseAmount } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useWorkspace } from '@/lib/workspace'

const NONE = '__none__'

interface Leg {
  key: string
  id?: string
  description: string
  amount: string
  category_id: string | null
}

const fromServer = (child: Transaction): Leg => ({
  key: child.id,
  id: child.id,
  description: child.description,
  amount: amountInput(child.amount_cents),
  category_id: child.category_id,
})

const cents = (leg: Leg) => parseAmount(leg.amount) ?? 0

export function SplitEditor({
  transaction,
  categories,
  onChanged,
}: {
  transaction: Transaction
  categories: CategoryRef[]
  onChanged: () => void
}) {
  const { profile } = useWorkspace()
  const queryClient = useQueryClient()
  const { data: children, isPending } = useQuery(splitsQuery(profile?.id, transaction.id))
  // No draft means the editor is showing exactly what the server has.
  const [draft, setDraft] = useState<Leg[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  const legs = draft ?? (children ?? []).map(fromServer)
  const total = legs.reduce((sum, leg) => sum + cents(leg), 0)
  const left = transaction.amount_cents - total
  const dirty = draft !== null

  const save = useMutation({
    mutationFn: (children: SplitChild[]) => {
      if (!profile) throw new Error('No profile is active yet.')
      return saveSplits(profile.id, transaction.id, children)
    },
    onSuccess: async () => {
      setDraft(null)
      setError(null)
      await queryClient.invalidateQueries(splitsQuery(profile?.id, transaction.id))
      onChanged()
    },
    onError: (failure: Error) => setError(failure.message),
  })

  const edit = (next: Leg[]) => {
    setError(null)
    setDraft(next)
  }
  const patch = (key: string, fields: Partial<Leg>) =>
    edit(legs.map((leg) => (leg.key === key ? { ...leg, ...fields } : leg)))
  const add = () =>
    edit([
      ...legs,
      {
        key: `new-${Date.now()}`,
        // A new leg starts with whatever is still missing, so the sum works out by itself.
        description: legs.length === 0 ? transaction.description : '',
        amount: amountInput(legs.length === 0 ? transaction.amount_cents : left),
        category_id: null,
      },
    ])

  const submit = (children: SplitChild[]) => save.mutate(children)

  if (isPending) {
    return (
      <div className="flex items-center gap-2 px-10 py-3 text-muted-foreground text-xs">
        <Spinner className="size-3.5" /> Loading the split...
      </div>
    )
  }

  return (
    <div className="border-t bg-muted/30 px-3 py-3 sm:px-10">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 pb-2">
        <h3 className="font-medium text-xs">Split of {formatEur(transaction.amount_cents)}</h3>
      </div>

      {legs.length === 0 ? (
        <p className="pb-2 text-muted-foreground text-xs">
          One booking, one category. Add a leg to spread it over several; queries count the legs, not
          the booking.
        </p>
      ) : (
        <ul className="space-y-1.5 pb-2">
          {legs.map((leg) => (
            <li className="flex flex-wrap items-center gap-2" key={leg.key}>
              <Input
                aria-label="Leg description"
                // A fixed width, not the width of the table: every field of a leg has to be
                // reachable without scrolling the table sideways first.
                className="h-7 w-64 min-w-40"
                onChange={(event) => patch(leg.key, { description: event.target.value })}
                placeholder="What was it for"
                value={leg.description}
              />
              <Input
                aria-label="Leg amount in euros"
                className="h-7 w-24 text-right tabular-nums"
                onChange={(event) => patch(leg.key, { amount: event.target.value })}
                value={leg.amount}
              />
              <Select
                onValueChange={(next) => patch(leg.key, { category_id: next === NONE ? null : next })}
                value={leg.category_id ?? NONE}
              >
                <SelectTrigger aria-label="Leg category" className="h-7! w-40" size="sm">
                  <SelectValue placeholder="Needs review" />
                </SelectTrigger>
                <SelectContent className="max-h-72">
                  <SelectItem value={NONE}>Needs review</SelectItem>
                  <SelectSeparator />
                  {categories.map((category) => (
                    <SelectItem key={category.id} value={category.id}>
                      {category.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Button
                onClick={() => edit(legs.filter((other) => other.key !== leg.key))}
                size="icon-sm"
                title="Remove this leg"
                variant="ghost"
              >
                <TrashIcon />
                <span className="sr-only">Remove this leg</span>
              </Button>
            </li>
          ))}
        </ul>
      )}

      <div className="flex flex-wrap items-center gap-2 pt-1">
        <Button onClick={add} size="sm" variant="outline">
          <PlusIcon /> Add a leg
        </Button>
        {legs.length > 0 && (
          // The server refuses a split whose legs miss the transaction, and it says so in its
          // own number format. The hint next to this button already has the figure, so the
          // editor refuses in place instead of asking. One leg is not a split either, and
          // "Remove the split" is the button for what that user means.
          <Button
            disabled={save.isPending || left !== 0 || legs.length < 2}
            onClick={() => submit(legs.map(toChild))}
            size="sm"
            title={
              legs.length < 2
                ? 'A split needs at least two legs.'
                : left === 0
                  ? undefined
                  : `${formatEur(left)} is still unaccounted for.`
            }
          >
            {save.isPending ? 'Saving...' : 'Save split'}
          </Button>
        )}
        {dirty && (
          <Button
            onClick={() => {
              setDraft(null)
              setError(null)
            }}
            size="sm"
            variant="ghost"
          >
            Reset
          </Button>
        )}
        {(children ?? []).length > 0 && !dirty && (
          <Button disabled={save.isPending} onClick={() => submit([])} size="sm" variant="ghost">
            Remove the split
          </Button>
        )}
        {legs.length > 0 && (
          // Next to the buttons, not at the far right: the row is as wide as the table it sits
          // in, and at 1024 the right end of it is off screen.
          <span className="text-xs tabular-nums">
            <span className="text-muted-foreground">Legs add up to </span>
            {formatEur(total)}
            {left !== 0 && (
              <span className="text-destructive"> · {formatEur(left)} unaccounted for</span>
            )}
          </span>
        )}
      </div>

      {error && (
        <p className={cn('pt-2 text-destructive text-xs')} role="alert">
          {error}
        </p>
      )}
    </div>
  )
}

const toChild = (leg: Leg): SplitChild => ({
  id: leg.id,
  description: leg.description,
  amount_cents: cents(leg),
  category_id: leg.category_id,
})
