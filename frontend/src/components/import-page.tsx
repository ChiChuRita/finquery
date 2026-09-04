import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { CheckCircle2Icon, InfoIcon, SparklesIcon, UploadCloudIcon, XIcon } from 'lucide-react'
import { useRef, useState, type DragEvent } from 'react'

import { DuplicateCandidates } from '@/components/duplicate-candidates'
import { ImportsList } from '@/components/imports-list'
import { MappingEditor } from '@/components/mapping-editor'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Spinner } from '@/components/ui/spinner'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import {
  categorizeImport,
  commitImport,
  conversationsQuery,
  decideDuplicates,
  importDuplicates,
  importsQuery,
  openReviewConversation,
  previewImport,
  type CategorizeReport,
  type CsvMapping,
  type DuplicateDecided,
  type ImportDuplicates,
  type ImportPreview,
  type ImportRecord,
} from '@/lib/api'
import { formatDate, formatEur } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useWorkspace } from '@/lib/workspace'

const lookedUp = (count: number) => (count === 1 ? '1 merchant was' : `${count} merchants were`)

function MappingBadge({ preview }: { preview: ImportPreview }) {
  if (preview.mapping_source === 'model') {
    return (
      <Badge variant="outline">
        <SparklesIcon /> Proposed by the fast model
      </Badge>
    )
  }
  if (preview.mapping_source === 'user') return <Badge variant="outline">Your mapping</Badge>
  return <Badge variant="secondary">{preview.preset_label} preset</Badge>
}

function PreviewTable({ rows }: { rows: ImportPreview['rows'] }) {
  return (
    <div className="rounded-xl border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-28">Date</TableHead>
            <TableHead>Description</TableHead>
            <TableHead>Counterparty</TableHead>
            <TableHead className="text-right">Amount</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row, index) => (
            <TableRow key={`${row.booked_on}-${index}`}>
              <TableCell className="whitespace-nowrap tabular-nums">{formatDate(row.booked_on)}</TableCell>
              <TableCell className="max-w-[22rem] truncate" title={row.description}>
                {row.description}
              </TableCell>
              <TableCell className="max-w-[14rem] truncate text-muted-foreground">{row.counterparty ?? '—'}</TableCell>
              <TableCell
                className={cn(
                  'whitespace-nowrap text-right tabular-nums',
                  row.amount_cents > 0 ? 'text-primary' : 'text-foreground',
                )}
              >
                {formatEur(row.amount_cents)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}

export function ImportPage() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const { profile, openTab } = useWorkspace()
  const fileInput = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<ImportPreview | null>(null)
  const [accountName, setAccountName] = useState('')
  const [dragging, setDragging] = useState(false)
  const [done, setDone] = useState<ImportRecord | null>(null)
  const [report, setReport] = useState<CategorizeReport | null>(null)
  // The bookings the commit held aside, and what the user has said about them so far.
  const [duplicates, setDuplicates] = useState<ImportDuplicates | null>(null)
  const [choices, setChoices] = useState<Record<string, 'keep' | 'remove'>>({})
  const [decided, setDecided] = useState<DuplicateDecided | null>(null)

  const previewMutation = useMutation({
    mutationFn: ({ chosen, mapping }: { chosen: File; mapping?: CsvMapping }) =>
      previewImport(chosen, mapping, mapping ? accountName : undefined),
    onSuccess: (next) => {
      setPreview(next)
      if (next.mapping_source !== 'user') setAccountName(next.account_name)
    },
  })

  const startReview = async (importId: string, profileId: string) => {
    const review = await openReviewConversation(importId, profileId)
    void queryClient.invalidateQueries(conversationsQuery(profileId))
    openTab(review.conversation_id)
    await navigate({ to: '/c/$conversationId', params: { conversationId: review.conversation_id } })
  }

  // Commit, then categorize, then hand the leftovers to a conversation: one flow, because a
  // fresh import is only useful once its rows have categories. A commit that held bookings
  // aside as possible duplicates stops on this page first: a booking nobody has decided about
  // is not in the data yet, so there is nothing to categorize about it.
  const commitMutation = useMutation({
    mutationFn: async ({ chosen, mapping }: { chosen: File; mapping: CsvMapping }) => {
      if (!profile) throw new Error('No profile is active yet.')
      // The rows land in the profile the sidebar is showing, which is also the one the list reads.
      const record = await commitImport(profile.id, chosen, mapping, accountName)
      setDone(record)
      clear()
      void queryClient.invalidateQueries(importsQuery(profile.id))
      const categorized = await categorizeImport(record.id, profile.id)
      setReport(categorized)
      if (record.duplicate_count > 0) {
        setDuplicates(await importDuplicates(record.id, profile.id))
        return
      }
      if (categorized.uncertain.length === 0) return
      await startReview(record.id, profile.id)
    },
  })

  // Keep both inserts the booking and categorizes it, Remove leaves the data alone. Both
  // happen on the server; this only asks, then reads the rest of the list back.
  const decideMutation = useMutation({
    mutationFn: async ({ removeAllExact }: { removeAllExact?: boolean }) => {
      if (!profile || !duplicates) throw new Error('No import is waiting for a decision.')
      const result = await decideDuplicates(
        duplicates.import_id,
        profile.id,
        removeAllExact ? [] : Object.entries(choices).map(([ref, decision]) => ({ ref, decision })),
        removeAllExact ?? false,
      )
      setDecided(result)
      setChoices({})
      void queryClient.invalidateQueries(importsQuery(profile.id))
      const next = await importDuplicates(duplicates.import_id, profile.id)
      setDuplicates(next.pending > 0 ? next : null)
      if (next.pending > 0) return
      if ((report?.uncertain.length ?? 0) === 0 && result.needs_review === 0) return
      await startReview(duplicates.import_id, profile.id)
    },
  })

  const clear = () => {
    setFile(null)
    setPreview(null)
    setAccountName('')
    previewMutation.reset()
    if (fileInput.current) fileInput.current.value = ''
  }

  const take = (chosen: File | undefined) => {
    if (!chosen) return
    setDone(null)
    setReport(null)
    setDuplicates(null)
    setChoices({})
    setDecided(null)
    setPreview(null)
    setAccountName('')
    commitMutation.reset()
    setFile(chosen)
    previewMutation.mutate({ chosen })
  }

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    setDragging(false)
    take(event.dataTransfer.files[0])
  }

  const error = previewMutation.error ?? commitMutation.error ?? decideMutation.error
  const busy = previewMutation.isPending || commitMutation.isPending

  return (
    <div className="flex h-full flex-col overflow-y-auto">
      <header className="flex h-14 shrink-0 items-center gap-3 border-b px-6">
        <h1 className="font-heading font-semibold text-sm">Import</h1>
        <p className="truncate text-muted-foreground text-xs">
          Drop a CSV export, check the mapping, then commit. Nothing is stored until you do.
        </p>
      </header>

      <div className="mx-auto w-full max-w-4xl space-y-6 px-6 py-6">
        <div
          className={cn(
            'rounded-2xl border border-dashed px-6 py-10 text-center transition-colors',
            dragging ? 'border-primary bg-primary/5' : 'bg-card',
          )}
          onDragLeave={() => setDragging(false)}
          onDragOver={(event) => {
            event.preventDefault()
            setDragging(true)
          }}
          onDrop={onDrop}
        >
          <UploadCloudIcon aria-hidden="true" className="mx-auto size-7 text-muted-foreground" />
          <p className="mt-3 font-medium text-sm">Drag a bank CSV export here</p>
          <p className="mt-1 text-muted-foreground text-xs">
            Sparkasse, DKB, ING, N26, comdirect and Trade Republic are recognized by their headers. Any other
            bank gets a mapping proposed by the fast model.
          </p>
          <input
            accept=".csv,text/csv,text/plain"
            className="sr-only"
            id="csv-file"
            onChange={(event) => take(event.target.files?.[0])}
            ref={fileInput}
            type="file"
          />
          <Button asChild className="mt-4" size="sm" variant="outline">
            <Label htmlFor="csv-file">Choose a file</Label>
          </Button>
        </div>

        {busy && (
          <div className="flex items-center gap-2 text-muted-foreground text-sm">
            <Spinner className="size-4" />
            {commitMutation.isPending
              ? 'Importing rows, then categorizing by your rules, the merchant dictionary and the fast model...'
              : 'Reading the file...'}
          </div>
        )}

        {error && (
          <div
            className="rounded-xl border border-destructive/40 bg-destructive/5 px-4 py-3 text-destructive text-sm"
            role="alert"
          >
            {error.message}
          </div>
        )}

        {done && (
          // Nothing imported is news, not success: the same file twice ends here with a green
          // tick over "Imported 0 of 433 rows", which reads like something went right.
          <div className="flex items-start gap-3 rounded-xl border bg-card px-4 py-3 text-sm">
            {done.imported_count === 0 ? (
              <InfoIcon aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
            ) : (
              <CheckCircle2Icon aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-primary" />
            )}
            <div>
              <p className="font-medium">
                {done.imported_count === 0
                  ? `No new rows for ${done.account_name}`
                  : `Imported ${done.imported_count} of ${done.row_count} rows into ${done.account_name}`}
              </p>
              <p className="text-muted-foreground text-xs">
                {done.duplicate_count > 0
                  ? `${done.duplicate_count} rows look like bookings you already have, so nothing was ` +
                    'added for them until you decide below. '
                  : ''}
                {done.imported_count === 0
                  ? 'Nothing was added, so nothing was categorized.'
                  : report
                    ? `${report.by_rule} categorized by your rules, ${report.by_dictionary} by the merchant ` +
                      `dictionary${report.lookups > 0 ? `, ${report.by_lookup} by web lookup` : ''} and ` +
                      `${report.by_model} by the categorizer. ${report.needs_review} rows across ` +
                      `${report.uncertain.length} merchants are Needs review.` +
                      (report.lookups > 0
                        ? ` ${lookedUp(report.lookups)} looked up on the web` +
                          `${report.lookups_refused > 0 ? `, ${report.lookups_refused} were not because only a person's name was left` : ''}.`
                        : '')
                    : 'Every new row is Needs review until it is categorized.'}
              </p>
            </div>
            <Button className="ml-auto" onClick={() => setDone(null)} size="icon-sm" variant="ghost">
              <XIcon />
              <span className="sr-only">Dismiss</span>
            </Button>
          </div>
        )}

        {duplicates && (
          <DuplicateCandidates
            busy={decideMutation.isPending}
            choices={choices}
            decided={decided}
            duplicates={duplicates}
            onApply={() => decideMutation.mutate({})}
            onChoose={(ref, choice) => setChoices((previous) => ({ ...previous, [ref]: choice }))}
            onRemoveAllExact={() => decideMutation.mutate({ removeAllExact: true })}
          />
        )}

        {file && preview && (
          <section className="space-y-5 rounded-2xl border bg-card p-5">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="font-heading font-semibold text-sm">{preview.file_name}</h2>
              <MappingBadge preview={preview} />
              <span className="text-muted-foreground text-xs">
                {preview.row_count} rows · {preview.encoding} · delimiter {JSON.stringify(preview.delimiter)}
              </span>
            </div>
            <p className="text-muted-foreground text-xs">{preview.note}</p>

            <MappingEditor
              header={preview.header}
              mapping={preview.mapping}
              onChange={(mapping) => previewMutation.mutate({ chosen: file, mapping })}
            />

            <div className="space-y-2">
              <h3 className="font-medium text-xs">First {preview.rows.length} rows with this mapping</h3>
              <PreviewTable rows={preview.rows} />
              {preview.issues.length > 0 && (
                <ul className="space-y-1 text-destructive text-xs">
                  {preview.issues.slice(0, 5).map((issue) => (
                    <li key={issue}>{issue}</li>
                  ))}
                </ul>
              )}
            </div>

            <div className="flex flex-wrap items-end justify-between gap-3 border-t pt-4">
              <div className="space-y-1.5">
                <Label className="text-muted-foreground text-xs" htmlFor="account-name">
                  Account
                </Label>
                <Input
                  className="w-64"
                  id="account-name"
                  onChange={(event) => setAccountName(event.target.value)}
                  value={accountName}
                />
              </div>
              <div className="flex items-center gap-2">
                <Button onClick={clear} size="sm" variant="ghost">
                  Cancel
                </Button>
                <Button
                  disabled={busy || !accountName.trim() || preview.rows.length === 0}
                  onClick={() => commitMutation.mutate({ chosen: file, mapping: preview.mapping })}
                  size="sm"
                >
                  Import {preview.row_count} rows
                </Button>
              </div>
            </div>
          </section>
        )}

        <ImportsList />
      </div>
    </div>
  )
}
