import { Tool, ToolContent, ToolHeader } from '@/components/ai-elements/tool'
import { Section } from '@/components/query-result'
import { Badge } from '@/components/ui/badge'
import type { RememberPart } from '@/lib/api'

const KINDS: Record<string, string> = { rule: 'Rule', preference: 'Preference', fact: 'Fact' }

/** The `remember` tool: the durable fact the turn stored, and what the profile did with it. */
export function MemoryToolStep({ part }: { part: RememberPart }) {
  const text = part.state === 'input-streaming' ? undefined : part.input?.text
  const kind = part.state === 'input-streaming' ? undefined : part.input?.kind
  return (
    <Tool className="mb-0 w-full">
      <ToolHeader
        state={part.state}
        title={part.state === 'output-available' ? 'Remembered for every chat' : 'Remembering'}
        type="tool-remember"
      />
      <ToolContent>
        <p className="text-muted-foreground text-xs">
          A durable fact, shared by every conversation of this profile. The Memory page lists them
          all and lets you change or forget any of them.
        </p>
        <Section label="Memory">
          <div className="flex flex-wrap items-baseline gap-2">
            <p className="text-sm">{text ?? 'Writing it down...'}</p>
            {kind && <Badge variant="secondary">{KINDS[kind] ?? kind}</Badge>}
          </div>
        </Section>
        {part.state === 'output-available' && (
          <Section label="Result">
            <p className="text-muted-foreground text-sm">{part.output}</p>
          </Section>
        )}
        {part.state === 'output-error' && (
          <Section label="Error">
            <p className="rounded-md bg-destructive/10 px-3 py-2 text-destructive text-sm">{part.errorText}</p>
          </Section>
        )}
      </ToolContent>
    </Tool>
  )
}
