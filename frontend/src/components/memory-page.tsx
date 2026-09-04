import { useQuery, useQueryClient } from '@tanstack/react-query'
import { BrainIcon, PencilIcon, Trash2Icon } from 'lucide-react'
import { useState } from 'react'

import { ConfirmDialog } from '@/components/dialogs'
import { DocumentPage } from '@/components/page'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import { Textarea } from '@/components/ui/textarea'
import { deleteMemory, memoriesQuery, patchMemory, type Memory, type MemoryKind } from '@/lib/api'
import { formatDateTime } from '@/lib/format'
import { useWorkspace } from '@/lib/workspace'

const KIND_LABEL: Record<MemoryKind, string> = { fact: 'Fact', preference: 'Preference', rule: 'Rule' }
const SOURCE_LABEL: Record<Memory['source'], string> = { distilled: 'picked up in a chat', explicit: 'you asked for it' }

export function MemoryPage() {
  const { profile } = useWorkspace()
  const queryClient = useQueryClient()
  const { data: memories } = useQuery(memoriesQuery(profile?.id))
  const [editing, setEditing] = useState<string>()
  const [deleting, setDeleting] = useState<Memory>()

  const refresh = () => queryClient.invalidateQueries(memoriesQuery(profile?.id))

  const save = async (memory: Memory, text: string) => {
    setEditing(undefined)
    if (!text.trim() || text.trim() === memory.text) return
    await patchMemory(memory.id, { text: text.trim() })
    await refresh()
  }

  const remove = async (memory: Memory) => {
    await deleteMemory(memory.id)
    await refresh()
  }

  return (
    <DocumentPage
      description="What the assistant knows about you in every conversation of this profile. At most five of these travel with a question, chosen by how well they match it."
      title="Memory"
    >
      <section className="flex flex-col gap-3">
        <div className="flex items-baseline justify-between">
          <h2 className="font-heading font-semibold text-sm">Remembered facts</h2>
          {memories && memories.length > 0 && (
            <span className="text-muted-foreground text-xs">{memories.length} in this profile</span>
          )}
        </div>

        {!memories || memories.length === 0 ? (
          <Empty className="border">
            <EmptyHeader>
              <EmptyMedia variant="icon">
                <BrainIcon aria-hidden="true" />
              </EmptyMedia>
              <EmptyTitle>Nothing remembered yet</EmptyTitle>
              <EmptyDescription>
                Tell the assistant something durable, like what a merchant is or that PayPal to Anna is dinner,
                and it appears here.
              </EmptyDescription>
            </EmptyHeader>
          </Empty>
        ) : (
          <ul className="divide-y rounded-xl border">
            {memories.map((memory) => (
              <li className="group flex items-start gap-3 px-4 py-3" key={memory.id}>
                <Badge className="mt-0.5 shrink-0" variant={memory.kind === 'fact' ? 'outline' : 'secondary'}>
                  {KIND_LABEL[memory.kind]}
                </Badge>
                <div className="min-w-0 flex-1">
                  {editing === memory.id ? (
                    <Textarea
                      aria-label="Memory text"
                      autoFocus
                      className="min-h-16 text-sm"
                      defaultValue={memory.text}
                      onBlur={(event) => void save(memory, event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter' && !event.shiftKey) {
                          event.preventDefault()
                          void save(memory, event.currentTarget.value)
                        }
                        if (event.key === 'Escape') setEditing(undefined)
                      }}
                    />
                  ) : (
                    <button
                      className="w-full rounded-sm text-left text-sm transition-colors hover:text-primary focus-ring"
                      onClick={() => setEditing(memory.id)}
                      title="Click to edit"
                      type="button"
                    >
                      {memory.text}
                    </button>
                  )}
                  <p className="pt-1 text-2xs text-muted-foreground">
                    {SOURCE_LABEL[memory.source]} &middot; {formatDateTime(memory.created_at)}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-1 opacity-0 transition-opacity focus-within:opacity-100 group-hover:opacity-100">
                  <Button aria-label="Edit this memory" onClick={() => setEditing(memory.id)} size="icon-xs" variant="ghost">
                    <PencilIcon />
                  </Button>
                  <Button aria-label="Delete this memory" onClick={() => setDeleting(memory)} size="icon-xs" variant="ghost">
                    <Trash2Icon />
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <ConfirmDialog
        action="Forget it"
        description={`"${deleting?.text ?? ''}" is dropped and no later answer will use it.`}
        onConfirm={async () => {
          if (deleting) await remove(deleting)
        }}
        onOpenChange={(open) => setDeleting(open ? deleting : undefined)}
        open={deleting !== undefined}
        title="Forget this memory?"
      />
    </DocumentPage>
  )
}
