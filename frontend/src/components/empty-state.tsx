import { useQuery } from '@tanstack/react-query'

import { Suggestion } from '@/components/ai-elements/suggestion'
import { transactionCountQuery } from '@/lib/api'
import { useWorkspace } from '@/lib/workspace'

export const STARTER_SUGGESTIONS = [
  'What can you help me with?',
  'How much did I spend on groceries in May?',
  'Which subscriptions am I paying for?',
  'Compare my spending in April and May',
]

/** Nothing imported yet, so nothing to count. The one question that still has an answer; the
 *  way out of an empty profile is the composer right below, not a page somewhere else. */
const NO_DATA_SUGGESTIONS = ['What can you help me with?']

export function EmptyState({ onPick }: { onPick: (text: string) => void }) {
  const { profile } = useWorkspace()
  const { data: bookings } = useQuery(transactionCountQuery(profile?.id))
  const empty = bookings === 0

  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-6 py-16 text-center">
      <div className="space-y-2">
        <h2 className="font-heading font-semibold text-2xl tracking-tight md:text-3xl">
          What do you want to know about your money?
        </h2>
        <p className="mx-auto max-w-md text-balance text-muted-foreground text-sm">
          Drop your bank statements into the chat, then ask in your own words. Every number in an answer comes
          from a query you can inspect.
        </p>
      </div>
      {/* While the count is on its way there is nothing honest to offer, so nothing is offered. */}
      {bookings !== undefined && (
        <div className="flex max-w-2xl flex-col items-center gap-4">
          <div className="flex flex-wrap items-center justify-center gap-2">
            {(empty ? NO_DATA_SUGGESTIONS : STARTER_SUGGESTIONS).map((s) => (
              <Suggestion key={s} onClick={onPick} suggestion={s} />
            ))}
          </div>
          {/* `text-balance` breaks this one after "Drop a CSV": at this length an evenly
              balanced block reads worse than plain prose. */}
          {empty && (
            <p className="max-w-lg text-pretty text-muted-foreground text-sm">
              Nothing is imported in this profile yet. Drop a CSV export, a statement PDF or a bill photo
              into the box below and I will read it and ask about anything I am unsure of.
            </p>
          )}
        </div>
      )}
    </div>
  )
}
