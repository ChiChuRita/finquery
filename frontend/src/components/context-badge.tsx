import {
  Context,
  ContextContent,
  ContextContentBody,
  ContextContentHeader,
  ContextTrigger,
} from '@/components/ai-elements/context'
import { slotLabel, type ContextStats } from '@/lib/api'

/** How much of the model's context the conversation fills. Hover for the breakdown. */
export function ContextBadge({ stats }: { stats: ContextStats }) {
  return (
    <Context maxTokens={stats.budget} usedTokens={stats.used}>
      <ContextTrigger aria-label="Context usage" className="h-7 gap-1.5 rounded-full px-2 text-xs" />
      <ContextContent align="end" className="min-w-64">
        <ContextContentHeader />
        <ContextContentBody className="space-y-1.5">
          <Row label="Model" value={slotLabel(stats.slot) ?? stats.slot} />
          <Row label="Memories in prompt" value={stats.memories} />
          {stats.summarized_turns > 0 ? (
            <Row label="Turns summarized" value={stats.summarized_turns} />
          ) : (
            <p className="pt-1 text-2xs text-muted-foreground">
              Past 60 percent, turns older than the last six are summarized.
            </p>
          )}
        </ContextContentBody>
      </ContextContent>
    </Context>
  )
}

function Row({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex items-center justify-between gap-3 text-xs">
      <span className="text-muted-foreground">{label}</span>
      <span>{value}</span>
    </div>
  )
}
