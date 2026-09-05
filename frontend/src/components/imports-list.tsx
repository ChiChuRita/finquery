import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { FileSpreadsheetIcon, MessageSquareIcon, PlusIcon, Trash2Icon } from 'lucide-react'
import { useState, type ReactNode } from 'react'

import { ConfirmDialog } from '@/components/dialogs'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import {
  conversationsQuery,
  deleteImport,
  importsQuery,
  openReviewConversation,
  pendingDuplicates,
  type ImportRecord,
} from '@/lib/api'
import { formatDateTime } from '@/lib/format'
import { useWorkspace } from '@/lib/workspace'

const KIND_LABELS: Record<string, string> = { csv: 'CSV', pdf: 'Statement PDF', image: 'Photo' }

/** One counted thing about an import. The number is the point, so it carries the weight. */
function Stat({ label, value, note }: { label: string; value: number; note?: ReactNode }) {
  return (
    <div className="flex items-baseline gap-1.5">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="font-medium tabular-nums">
        {value}
        {note ? <span className="ml-1.5 font-normal">{note}</span> : null}
      </dd>
    </div>
  )
}

/** What one import brought in, and the two things that can still be done about it.
 *
 * Nothing is imported or decided here: the file was dropped into a chat and every question it
 * raised is a Question card in that conversation, which is where "Continue in chat" leads.
 */
function ImportCard({
  record,
  onContinue,
  onDelete,
  busy,
}: {
  record: ImportRecord
  onContinue: () => void
  onDelete: () => void
  busy: boolean
}) {
  const undecided = pendingDuplicates(record)
  const open = undecided > 0 || record.needs_review > 0
  return (
    <li className="rounded-xl border bg-card px-4 py-3">
      <div className="flex flex-wrap items-start gap-x-3 gap-y-2">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="truncate font-medium text-sm" title={record.file_name}>
              {record.file_name}
            </p>
            <Badge variant="secondary">{KIND_LABELS[record.kind] ?? record.kind}</Badge>
            {record.preset && <Badge variant="outline">{record.preset}</Badge>}
          </div>
          <p className="mt-0.5 truncate text-muted-foreground text-xs">
            {record.account_name} · {formatDateTime(record.created_at)}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {open && (
            <Button disabled={busy} onClick={onContinue} size="sm" variant="outline">
              <MessageSquareIcon data-icon="inline-start" />
              Continue in chat
            </Button>
          )}
          <Button
            className="text-muted-foreground hover:text-destructive"
            disabled={busy}
            onClick={onDelete}
            size="icon-sm"
            title="Delete this import and the bookings it brought in"
            variant="ghost"
          >
            <Trash2Icon />
            <span className="sr-only">Delete {record.file_name}</span>
          </Button>
        </div>
      </div>

      <dl className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-xs">
        <Stat label="Rows read" value={record.row_count} />
        <Stat label="Imported" value={record.imported_count} />
        <Stat
          label="Duplicates"
          note={
            undecided > 0 ? (
              // Undecided candidates are the one number nobody should walk past: those bookings
              // are neither in the data nor thrown away until the user says.
              <span className="text-amber-600 dark:text-amber-500">{undecided} undecided</span>
            ) : record.duplicate_count > 0 ? (
              <span className="text-muted-foreground">
                {record.duplicates_kept} kept, {record.duplicates_removed} removed
              </span>
            ) : undefined
          }
          value={record.duplicate_count}
        />
        <Stat label="Needs review" value={record.needs_review} />
      </dl>

      {record.reconciliation && (
        <p className="mt-2 text-muted-foreground text-xs">Reconciliation: {record.reconciliation}</p>
      )}
    </li>
  )
}

/** The imports of this profile: what each one came to, with a way back in and a way out. */
export function ImportsList() {
  const { profile, openTab } = useWorkspace()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const { data: imports } = useQuery(importsQuery(profile?.id))
  const [doomed, setDoomed] = useState<ImportRecord | null>(null)
  const [error, setError] = useState<string>()

  // The conversation the file was dropped into, or, for an import that was committed outside a
  // chat, a conversation seeded with the card it is waiting on. Either way the question is
  // asked where every other question is asked.
  const goOn = useMutation({
    mutationFn: async (record: ImportRecord) => {
      if (!profile) throw new Error('No profile is active yet.')
      let conversationId = record.conversation_id
      if (!conversationId) {
        const review = await openReviewConversation(record.id, profile.id)
        conversationId = review.conversation_id
        await queryClient.invalidateQueries(conversationsQuery(profile.id))
      }
      openTab(conversationId)
      await navigate({ to: '/c/$conversationId', params: { conversationId } })
    },
    onError: (failure) => setError(failure.message),
  })

  // Deleting takes the bookings with it, so every list that counts them has to be re-read.
  const remove = useMutation({
    mutationFn: async (record: ImportRecord) => {
      if (!profile) throw new Error('No profile is active yet.')
      await deleteImport(record.id, profile.id)
      await queryClient.invalidateQueries(importsQuery(profile.id))
      await queryClient.invalidateQueries({ queryKey: ['transactions'] })
    },
    onError: (failure) => setError(failure.message),
  })

  const busy = goOn.isPending || remove.isPending

  return (
    <section className="space-y-3">
      <div className="flex items-baseline justify-between">
        <h2 className="font-heading font-semibold text-sm">Past imports</h2>
        <span className="flex items-center gap-2 text-muted-foreground text-xs">
          {busy && <Spinner className="size-3.5" />}
          {imports && imports.length > 0 ? `${imports.length} in this profile` : null}
        </span>
      </div>

      {error && (
        <p className="text-destructive text-xs" role="alert">
          {error}
        </p>
      )}

      {!imports || imports.length === 0 ? (
        <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed px-6 py-10 text-center">
          <FileSpreadsheetIcon aria-hidden="true" className="size-5 text-muted-foreground" />
          <div className="space-y-1">
            <p className="font-medium text-sm">Nothing imported yet</p>
            <p className="mx-auto max-w-md text-balance text-muted-foreground text-xs">
              Drop a CSV export, a statement PDF or a bill photo into the chat. The assistant reads it, asks
              about anything it is unsure of and imports it, and every import shows up here.
            </p>
          </div>
          <Button onClick={() => void navigate({ to: '/' })} size="sm" variant="outline">
            <PlusIcon data-icon="inline-start" />
            New chat
          </Button>
        </div>
      ) : (
        <ul className="space-y-2">
          {imports.map((record) => (
            <ImportCard
              busy={busy}
              key={record.id}
              onContinue={() => {
                setError(undefined)
                goOn.mutate(record)
              }}
              onDelete={() => {
                setError(undefined)
                setDoomed(record)
              }}
              record={record}
            />
          ))}
        </ul>
      )}

      <ConfirmDialog
        action="Delete import"
        description={
          doomed
            ? `The ${doomed.imported_count} bookings ${doomed.file_name} added to ${doomed.account_name} are deleted with it` +
              `${doomed.duplicate_count > 0 ? `, and so are its ${doomed.duplicate_count} duplicate candidates` : ''}. ` +
              'Bookings from other imports stay. This cannot be undone.'
            : ''
        }
        onConfirm={async () => {
          if (doomed) await remove.mutateAsync(doomed).catch(() => undefined)
        }}
        onOpenChange={(open) => setDoomed(open ? doomed : null)}
        open={doomed !== null}
        title="Delete this import?"
      />
    </section>
  )
}
