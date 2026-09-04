import {
  AlertTriangleIcon,
  CheckIcon,
  FileSpreadsheetIcon,
  HourglassIcon,
  ReceiptTextIcon,
} from 'lucide-react'

import { Tool, ToolContent, ToolHeader } from '@/components/ai-elements/tool'
import { Step } from '@/components/tool-step'
import { Badge } from '@/components/ui/badge'
import type { AddTransactionPart, ExtractTransactionPart, ImportFilePart, ImportProgress } from '@/lib/api'
import { formatEur } from '@/lib/format'

const bookings = (count: number) => (count === 1 ? '1 booking' : `${count} bookings`)

function title(part: ImportFilePart): string {
  const file = part.state === 'input-available' || part.state === 'input-streaming' ? part.input?.file_name : undefined
  if (part.state === 'output-error') return 'Import failed'
  if (part.state !== 'output-available') return file ? `Importing ${file}` : 'Importing the attached file'
  const output = part.output
  switch (output.status) {
    case 'imported':
      return `Imported ${bookings(output.imported)} from ${output.file}`
    case 'confirm_mapping':
      return `${output.file}: the column mapping needs your confirmation`
    case 'extraction_not_ready':
      return `${output.file} was stored, not read`
    case 'already_imported':
      return `${output.file} was already imported`
    default:
      return 'Nothing was imported'
  }
}

function Counts({ label, value, tone }: { label: string; value: number; tone?: 'review' }) {
  return (
    <div className="rounded-md border bg-muted/20 px-3 py-2">
      <p className={tone === 'review' && value > 0 ? 'font-medium text-amber-600 tabular-nums dark:text-amber-500' : 'font-medium tabular-nums'}>
        {value}
      </p>
      <p className="text-muted-foreground text-xs">{label}</p>
    </div>
  )
}

/** The progress lines the tool streamed while it worked. Live only: nothing is stored. */
function Progress({ lines }: { lines: ImportProgress[] }) {
  if (lines.length === 0) {
    return <p className="text-muted-foreground text-sm">Reading the file...</p>
  }
  return (
    <ol className="space-y-1 text-sm">
      {lines.map((line, index) => (
        <li
          className={index === lines.length - 1 ? 'flex items-center gap-2' : 'flex items-center gap-2 text-muted-foreground'}
          // The stage names repeat across imports but never inside one.
          key={line.stage}
        >
          {index === lines.length - 1 ? (
            <HourglassIcon className="size-3.5 shrink-0" />
          ) : (
            <CheckIcon className="size-3.5 shrink-0 text-primary" />
          )}
          {line.message}
        </li>
      ))}
    </ol>
  )
}

/** One `import_file` call: its progress while it runs, then what it made of the file. */
export function ImportToolStep({ part, progress }: { part: ImportFilePart; progress: ImportProgress[] }) {
  return (
    <Tool className="mb-0 w-full" defaultOpen={part.state !== 'output-available'}>
      <ToolHeader state={part.state} title={title(part)} type="tool-import_file" />
      <ToolContent>
        {part.state === 'output-error' ? (
          <p className="rounded-md bg-destructive/10 px-3 py-2 text-destructive text-sm">{part.errorText}</p>
        ) : part.state !== 'output-available' ? (
          <Progress lines={progress} />
        ) : part.output.status === 'imported' ? (
          <div className="space-y-3">
            <p className="text-sm">{part.output.summary}</p>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <Counts label="rows read" value={part.output.rows_read} />
              <Counts label="imported" value={part.output.imported} />
              <Counts label="already there" value={part.output.duplicates} />
              <Counts label="unreadable" value={part.output.unreadable_rows} />
              <Counts label="by your rules" value={part.output.categorized.by_rule} />
              <Counts label="by the merchant list" value={part.output.categorized.by_dictionary} />
              <Counts label="by the categorizer" value={part.output.categorized.by_model} />
              <Counts label="needs review" tone="review" value={part.output.categorized.needs_review} />
            </div>
            {part.output.categorized.error && (
              <p className="text-destructive text-xs">{part.output.categorized.error}</p>
            )}
          </div>
        ) : part.output.status === 'confirm_mapping' ? (
          <p className="text-sm">{part.output.note}</p>
        ) : 'message' in part.output ? (
          <p className="text-sm">{part.output.message}</p>
        ) : (
          <p className="rounded-md bg-destructive/10 px-3 py-2 text-destructive text-sm">{part.output.error}</p>
        )}
      </ToolContent>
    </Tool>
  )
}

/** `extract_transaction`: the line above the preview card, or why there was nothing to preview. */
export function PreviewToolStep({ part }: { part: ExtractTransactionPart }) {
  if (part.state !== 'output-available') {
    return (
      <Step>
        <ReceiptTextIcon className="size-3.5" />
        Reading the booking out of your message
      </Step>
    )
  }
  if (part.output.status !== 'preview') {
    return (
      <Step tone="error">
        <AlertTriangleIcon className="size-3.5" />
        {part.output.error}
      </Step>
    )
  }
  return (
    <Step>
      <ReceiptTextIcon className="size-3.5 text-primary" />
      <span className="text-foreground">
        {part.output.drafts.length === 1
          ? 'One booking to confirm'
          : `${part.output.drafts.length} bookings to confirm`}
      </span>
      {part.output.problems.length > 0 && (
        <Badge className="ml-auto" variant="secondary">
          {part.output.problems.length} line(s) skipped
        </Badge>
      )}
    </Step>
  )
}

/** `add_transaction`: the booking that was written, and where categorization put it. */
export function AddedToolStep({ part }: { part: AddTransactionPart }) {
  if (part.state !== 'output-available') {
    return (
      <Step>
        <FileSpreadsheetIcon className="size-3.5" />
        Adding the transaction
      </Step>
    )
  }
  const output = part.output
  if (output.status === 'no_such_draft') {
    return (
      <Step tone="error">
        <AlertTriangleIcon className="size-3.5" />
        {output.error}
      </Step>
    )
  }
  if (output.status === 'already_added') {
    return (
      <Step>
        <CheckIcon className="size-3.5" />
        {output.message}
      </Step>
    )
  }
  return (
    <Step>
      <CheckIcon className="size-3.5 text-primary" />
      <span className="text-foreground">
        Added <span className="font-medium">{output.description}</span>,{' '}
        <span className="tabular-nums">{formatEur(output.amount_cents)}</span> in {output.account}
      </span>
      <Badge className="ml-auto" variant={output.needs_review ? 'outline' : 'secondary'}>
        {output.needs_review
          ? 'Needs review'
          : `${output.category}${output.subcategory ? ` > ${output.subcategory}` : ''}`}
      </Badge>
    </Step>
  )
}
