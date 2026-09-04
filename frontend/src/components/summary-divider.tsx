import { useQueryClient } from '@tanstack/react-query'
import { ChevronDownIcon } from 'lucide-react'
import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Textarea } from '@/components/ui/textarea'
import { conversationQuery, patchConversation } from '@/lib/api'

/**
 * Where the rolling summary took over from the turns above it. The turns are still in the
 * transcript; only the prompt drops them. Editing the summary changes what the next turn sends.
 */
export function SummaryDivider({
  conversationId,
  summary,
  turns,
}: {
  conversationId: string
  summary: string
  turns: number
}) {
  const queryClient = useQueryClient()
  // The draft exists only while editing, so a compression that rewrites the summary underneath
  // is picked up without a draft of the old text lingering.
  const [draft, setDraft] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const save = async (text: string) => {
    if (!text.trim() || text.trim() === summary) {
      setDraft(null)
      return
    }
    setSaving(true)
    try {
      await patchConversation(conversationId, { summary: text.trim() })
      await queryClient.invalidateQueries(conversationQuery(conversationId))
      setDraft(null)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Collapsible className="w-full">
      <CollapsibleTrigger className="group flex w-full items-center gap-3 text-muted-foreground text-xs transition-colors hover:text-foreground">
        <span className="h-px flex-1 bg-border" />
        <span className="inline-flex items-center gap-1.5 rounded-full border border-dashed px-2.5 py-0.5">
          Earlier turns summarized
          <span className="text-muted-foreground/70">({turns})</span>
          <ChevronDownIcon className="size-3 transition-transform group-data-[state=open]:rotate-180" />
        </span>
        <span className="h-px flex-1 bg-border" />
      </CollapsibleTrigger>

      <CollapsibleContent className="pt-3">
        <div className="rounded-lg border border-dashed bg-muted/30 p-3">
          {draft !== null ? (
            <div className="space-y-2">
              <Textarea
                aria-label="Rolling summary"
                autoFocus
                className="min-h-32 bg-background text-sm"
                onChange={(event) => setDraft(event.target.value)}
                value={draft}
              />
              <div className="flex items-center justify-end gap-2">
                <Button disabled={saving} onClick={() => setDraft(null)} size="sm" variant="ghost">
                  Cancel
                </Button>
                <Button disabled={saving} onClick={() => void save(draft)} size="sm">
                  {saving ? 'Saving...' : 'Save summary'}
                </Button>
              </div>
            </div>
          ) : (
            <div className="space-y-2">
              <p className="whitespace-pre-wrap text-sm">{summary}</p>
              <div className="flex items-center justify-between gap-3">
                <p className="text-[11px] text-muted-foreground">
                  This replaces the turns above in the prompt. An edit is used on the next message.
                </p>
                <Button onClick={() => setDraft(summary)} size="sm" variant="outline">
                  Edit
                </Button>
              </div>
            </div>
          )}
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
}
