import { useQuery } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { UploadIcon } from 'lucide-react'

import { Suggestion } from '@/components/ai-elements/suggestion'
import { Button } from '@/components/ui/button'
import { transactionCountQuery } from '@/lib/api'
import { useWorkspace } from '@/lib/workspace'

export const STARTER_SUGGESTIONS = [
  'What can you help me with?',
  'How much did I spend on groceries in May?',
  'Which subscriptions am I paying for?',
  'Compare my spending in April and May',
]

/** Nothing imported yet, so nothing to count. The one question that still has an answer, and
 *  the way out of an empty profile, which is a button and not a question. */
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
          Import your bank statements, then ask in your own words. Every number in an answer comes from a query
          you can inspect.
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
          {empty && (
            <Button asChild size="sm" variant="outline">
              <Link to="/import">
                <UploadIcon /> Import a bank statement
              </Link>
            </Button>
          )}
        </div>
      )}
    </div>
  )
}
