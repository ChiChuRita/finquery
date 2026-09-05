import { Tool, ToolContent, ToolHeader } from '@/components/ai-elements/tool'
import { ErrorSection, Section } from '@/components/query-result'
import { Badge } from '@/components/ui/badge'
import type { ReviewBatchPart, SetRulePart } from '@/lib/api'
import { formatEur } from '@/lib/format'

const bookings = (count: number | undefined) => (count === 1 ? '1 booking' : `${count ?? 0} bookings`)
const merchants = (count: number) => (count === 1 ? '1 merchant' : `${count} merchants`)

const target = (category?: string, subcategory?: string | null) =>
  subcategory ? `${category} > ${subcategory}` : (category ?? '')

function ruleTitle(part: SetRulePart) {
  if (part.state === 'output-error') return 'Rule call could not be read'
  if (part.state !== 'output-available') {
    const pattern = part.state === 'input-available' ? part.input.pattern : undefined
    return pattern ? `Storing the rule for ${pattern}` : 'Storing the rule'
  }
  if (part.output.error) return 'Rule refused'
  return `Rule · ${part.output.pattern} is ${target(part.output.category, part.output.subcategory)}`
}

/** One stored category rule: what it matches, where it points, how many rows it moved. */
export function RuleToolStep({ part }: { part: SetRulePart }) {
  return (
    <Tool className="mb-0 w-full">
      <ToolHeader state={part.state} title={ruleTitle(part)} type="tool-set_rule" />
      <ToolContent>
        {part.state === 'output-error' ? (
          // A malformed call, which the agent retries by itself: the retry is the next step.
          <ErrorSection message={part.errorText ?? 'That rule call could not be read, so it was made again.'} />
        ) : part.state === 'output-available' ? (
          <RuleResult part={part} />
        ) : (
          <Section label="Pattern">
            <p className="text-sm">
              {part.state === 'input-available' ? part.input.pattern : 'Writing the rule...'}
            </p>
          </Section>
        )}
      </ToolContent>
    </Tool>
  )
}

function RuleResult({ part }: { part: SetRulePart & { state: 'output-available' } }) {
  const output = part.output
  if (output.error) return <ErrorSection message={output.error} />
  return (
    <>
      <Section label="Rule">
        <p className="text-sm">
          Every booking whose text contains <span className="font-medium">{output.pattern}</span> is{' '}
          <span className="font-medium">{target(output.category, output.subcategory)}</span>.
        </p>
      </Section>
      <Section label="Effect">
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <Badge variant="secondary">{bookings(output.updated)} recategorized</Badge>
          <span className="text-muted-foreground">
            of {bookings(output.matched)} matched · rule {output.rule}
          </span>
        </div>
      </Section>
      {output.sample && output.sample.length > 0 && (
        <Section label="Bookings it matched">
          <ul className="space-y-1 text-muted-foreground text-sm">
            {output.sample.map((line) => (
              <li className="truncate" key={line}>
                {line}
              </li>
            ))}
          </ul>
        </Section>
      )}
    </>
  )
}

/** The queue behind the next Question card: who is still waiting and what is being asked. */
export function ReviewToolStep({ part }: { part: ReviewBatchPart }) {
  if (part.state !== 'output-available') {
    return (
      <Tool className="mb-0 w-full">
        <ToolHeader state={part.state} title="Looking for what still needs review" type="tool-review_batch" />
        <ToolContent>
          <Section label="Review queue">
            <p className="text-muted-foreground text-sm">Counting the merchants without a category...</p>
          </Section>
        </ToolContent>
      </Tool>
    )
  }
  const { pending_merchants, questions } = part.output
  const title =
    pending_merchants === 0
      ? 'Nothing left to review'
      : `Review queue · ${merchants(pending_merchants)}, asking about ${questions.length}`
  return (
    <Tool className="mb-0 w-full">
      <ToolHeader state={part.state} title={title} type="tool-review_batch" />
      <ToolContent>
        {questions.length === 0 ? (
          <Section label="Review queue">
            <p className="text-muted-foreground text-sm">Every booking of this profile has a category.</p>
          </Section>
        ) : (
          <>
            <p className="text-muted-foreground text-xs">
              Bookings with no category, grouped by merchant. Each answer on the card below becomes
              a rule, so the same merchant is never asked about twice.
            </p>
            <Section label={`Asking about ${merchants(questions.length)}`}>
              <ul className="space-y-2">
                {questions.map((question) => (
                  <li className="flex flex-wrap items-baseline justify-between gap-x-3 text-sm" key={question.pattern}>
                    <span className="min-w-0 truncate font-medium">{question.label}</span>
                    <span className="text-muted-foreground text-xs">
                      {bookings(question.bookings)} · {formatEur(question.amount_cents)}
                      {question.guess ? ` · guess: ${question.guess}` : ''}
                    </span>
                  </li>
                ))}
              </ul>
            </Section>
          </>
        )}
      </ToolContent>
    </Tool>
  )
}
