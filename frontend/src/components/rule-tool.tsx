import { AlertTriangleIcon, ListChecksIcon, TagIcon } from 'lucide-react'

import { Step } from '@/components/tool-step'
import { Badge } from '@/components/ui/badge'
import type { ReviewBatchPart, SetRulePart } from '@/lib/api'

const bookings = (count: number | undefined) =>
  count === 1 ? '1 booking' : `${count ?? 0} bookings`

/** One stored category rule: what it matches, where it points, how many rows it moved. */
export function RuleToolStep({ part }: { part: SetRulePart }) {
  if (part.state === 'output-error') {
    // A malformed call, which the agent retries by itself: the retry is the next step.
    return (
      <Step tone="error">
        <AlertTriangleIcon className="size-3.5" />
        That rule call could not be read, so it was made again.
      </Step>
    )
  }
  if (part.state !== 'output-available') {
    const pattern = part.state === 'input-available' ? part.input.pattern : undefined
    return (
      <Step>
        <TagIcon className="size-3.5" />
        {pattern ? `Storing the rule for ${pattern}` : 'Storing the rule'}
      </Step>
    )
  }
  const output = part.output
  if (output.error) {
    return (
      <Step tone="error">
        <AlertTriangleIcon className="size-3.5" />
        {output.error}
      </Step>
    )
  }
  return (
    <Step>
      <TagIcon className="size-3.5 text-primary" />
      <span className="text-foreground">
        Rule: <span className="font-medium">{output.pattern}</span> is{' '}
        <span className="font-medium">
          {output.category}
          {output.subcategory ? ` > ${output.subcategory}` : ''}
        </span>
      </span>
      <Badge className="ml-auto" variant="secondary">
        {bookings(output.updated)} recategorized
      </Badge>
    </Step>
  )
}

/** The queue behind the next Question card. */
export function ReviewToolStep({ part }: { part: ReviewBatchPart }) {
  if (part.state !== 'output-available') {
    return (
      <Step>
        <ListChecksIcon className="size-3.5" />
        Looking for what still needs review
      </Step>
    )
  }
  const { pending_merchants, questions } = part.output
  return (
    <Step>
      <ListChecksIcon className="size-3.5" />
      {pending_merchants === 0
        ? 'Nothing left to review'
        : `${pending_merchants} merchant(s) need review, asking about ${questions.length}`}
    </Step>
  )
}
