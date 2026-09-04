import { useQuery, useQueryClient } from '@tanstack/react-query'
import { BrainIcon, PencilIcon, Trash2Icon } from 'lucide-react'
import { useState } from 'react'

import { ConfirmDialog } from '@/components/dialogs'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
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
    <div className="h-full overflow-y-auto">
      <div className="mx-auto w-full max-w-3xl px-6 py-10">
        <h1 className="font-heading font-semibold text-2xl tracking-tight">Memory</h1>
        <p className="mt-1 text-muted-foreground text-sm">
          What the assistant knows about you in every conversation of this profile. At most five of these travel
          with a question, chosen by how well they match it.
        </p>

        <section className="mt-6 space-y-3">
          <div className="flex items-baseline justify-between">
            <h2 className="font-heading font-semibold text-sm">Remembered facts</h2>
            {memories && memories.length > 0 && (
              <span className="text-muted-foreground text-xs">{memories.length} in this profile</span>
            )}
          </div>

          {!memories || memories.length === 0 ? (
            <div className="flex items-center gap-3 rounded-xl border border-dashed px-4 py-6 text-muted-foreground text-sm">
              <BrainIcon className="size-4 shrink-0" />
              Nothing remembered yet. Tell the assistant something durable, like what a merchant is or that PayPal
              to Anna is dinner, and it appears here.
            </div>
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
                        className="w-full text-left text-sm hover:text-primary"
                        onClick={() => setEditing(memory.id)}
                        title="Click to edit"
                        type="button"
                      >
                        {memory.text}
                      </button>
                    )}
                    <p className="pt-1 text-[11px] text-muted-foreground">
                      {SOURCE_LABEL[memory.source]} &middot; {formatDateTime(memory.created_at)}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-1 opacity-0 transition-opacity focus-within:opacity-100 group-hover:opacity-100">
                    <Button
                      aria-label="Edit this memory"
                      onClick={() => setEditing(memory.id)}
                      size="icon-xs"
                      variant="ghost"
                    >
                      <PencilIcon className="size-4" />
                    </Button>
                    <Button
                      aria-label="Delete this memory"
                      onClick={() => setDeleting(memory)}
                      size="icon-xs"
                      variant="ghost"
                    >
                      <Trash2Icon className="size-4" />
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

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
    </div>
  )
}
