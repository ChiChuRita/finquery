import { Suggestion } from '@/components/ai-elements/suggestion'

export const STARTER_SUGGESTIONS = [
  'What can you help me with?',
  'How much did I spend on groceries in May?',
  'Which subscriptions am I paying for?',
  'Compare my spending in April and May',
]

export function EmptyState({ onPick }: { onPick: (text: string) => void }) {
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
      <div className="flex max-w-2xl flex-wrap items-center justify-center gap-2">
        {STARTER_SUGGESTIONS.map((s) => (
          <Suggestion key={s} onClick={onPick} suggestion={s} />
        ))}
      </div>
    </div>
  )
}
