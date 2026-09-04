import { CheckIcon, CopyIcon } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import type { DuplicateCandidate, DuplicateDecided, ImportDuplicates } from '@/lib/api'
import { formatDate, formatEur } from '@/lib/format'
import { cn } from '@/lib/utils'

type Choice = 'keep' | 'remove'

const daysBetween = (candidate: DuplicateCandidate) => {
  if (!candidate.existing_booked_on) return 0
  const ms = Date.parse(candidate.booked_on) - Date.parse(candidate.existing_booked_on)
  return Math.round(Math.abs(ms) / 86_400_000)
}

/** What the booking it matched was, in the words the server recorded when it matched. */
function Matched({ candidate }: { candidate: DuplicateCandidate }) {
  const days = daysBetween(candidate)
  const when = candidate.existing_booked_on ? formatDate(candidate.existing_booked_on) : 'earlier'
  if (candidate.kind === 'exact') {
    return <>Already booked on {when}, same amount and text</>
  }
  return (
    <>
      Similar booking {days === 1 ? '1 day' : `${days} days`} apart ({when}):{' '}
      {candidate.existing_description}
    </>
  )
}

/** The candidates one import held aside, each answered with Keep both or Remove.
 *
 * The same question the chat asks on a Question card, on the page that made the import. It
 * writes nothing itself: the parent applies through the REST endpoint, which inserts what was
 * kept and categorizes it.
 */
export function DuplicateCandidates({
  duplicates,
  choices,
  onChoose,
  onApply,
  onRemoveAllExact,
  busy,
  decided,
}: {
  duplicates: ImportDuplicates
  choices: Record<string, Choice>
  onChoose: (ref: string, choice: Choice) => void
  onApply: () => void
  onRemoveAllExact: () => void
  busy: boolean
  decided: DuplicateDecided | null
}) {
  const answered = Object.keys(choices).length
  const more = duplicates.pending - duplicates.candidates.length

  return (
    <section className="space-y-4 rounded-2xl border border-primary/30 bg-primary/[0.03] p-5">
      <div className="flex items-start gap-2">
        <CopyIcon aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-primary" />
        <div className="min-w-0 space-y-1">
          <h2 className="font-heading font-semibold text-sm">
            {duplicates.pending === 1
              ? 'One booking may already be in this profile'
              : `${duplicates.pending} bookings may already be in this profile`}
          </h2>
          <p className="text-muted-foreground text-xs">
            Nothing was added for them and nothing was thrown away. Keep both inserts the booking into{' '}
            {duplicates.account_name}, Remove leaves your data as it is.
            {more > 0 ? ` Showing the first ${duplicates.candidates.length}, ${more} more after these.` : ''}
          </p>
        </div>
        <Badge className="ml-auto shrink-0" variant="secondary">
          {duplicates.exact} exact, {duplicates.near} near
        </Badge>
      </div>

      {duplicates.shortcut && (
        <div className="flex flex-wrap items-center gap-2 rounded-lg border bg-card px-3 py-2">
          <p className="min-w-0 flex-1 text-xs">
            {duplicates.exact} of them match an existing booking exactly, which is what re-importing the
            same statement looks like.
          </p>
          <Button disabled={busy} onClick={onRemoveAllExact} size="sm" variant="outline">
            Remove all {duplicates.exact} exact duplicates
          </Button>
        </div>
      )}

      <ul className="space-y-2">
        {duplicates.candidates.map((candidate) => {
          const choice = choices[candidate.ref]
          return (
            <li className="rounded-lg border bg-card p-3" key={candidate.ref}>
              <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                <div className="min-w-0">
                  <p className="truncate font-medium text-sm">{candidate.description}</p>
                  <p className="truncate text-muted-foreground text-xs">
                    <Matched candidate={candidate} />
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-2 text-xs">
                  <Badge variant={candidate.kind === 'exact' ? 'secondary' : 'outline'}>
                    {candidate.kind === 'exact' ? 'Exact' : 'Near'}
                  </Badge>
                  <span className="text-muted-foreground tabular-nums">{formatDate(candidate.booked_on)}</span>
                  <span className="tabular-nums">{formatEur(candidate.amount_cents)}</span>
                </div>
              </div>
              <div className="mt-2 flex flex-wrap gap-1.5">
                <Button
                  className={cn('h-7 text-xs', choice === 'keep' && 'ring-2 ring-primary')}
                  disabled={busy}
                  onClick={() => onChoose(candidate.ref, 'keep')}
                  size="sm"
                  variant={choice === 'keep' ? 'default' : 'outline'}
                >
                  Keep both
                </Button>
                <Button
                  className={cn('h-7 text-xs', choice === 'remove' && 'ring-2 ring-primary')}
                  disabled={busy}
                  onClick={() => onChoose(candidate.ref, 'remove')}
                  size="sm"
                  variant={choice === 'remove' ? 'default' : 'outline'}
                >
                  Remove
                </Button>
              </div>
            </li>
          )
        })}
      </ul>

      <div className="flex flex-wrap items-center justify-between gap-2 border-t pt-4">
        <p className="text-muted-foreground text-xs">
          {decided ? (
            <span className="inline-flex items-center gap-1.5">
              <CheckIcon aria-hidden="true" className="size-3 text-primary" />
              {decided.kept} kept, {decided.removed} removed so far.
            </span>
          ) : (
            'A booking stays out of your data until you decide.'
          )}
        </p>
        <div className="flex items-center gap-2">
          {busy && <Spinner className="size-4" />}
          <Button disabled={busy || answered === 0} onClick={onApply} size="sm">
            {answered === 1 ? 'Apply 1 decision' : `Apply ${answered} decisions`}
          </Button>
        </div>
      </div>
    </section>
  )
}
