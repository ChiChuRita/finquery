import {
  AlertTriangleIcon,
  CheckIcon,
  FileSpreadsheetIcon,
  HourglassIcon,
  ReceiptTextIcon,
  ScaleIcon,
} from 'lucide-react'

import { Tool, ToolContent, ToolHeader } from '@/components/ai-elements/tool'
import { ChangesetProposal } from '@/components/changeset-card'
import { Step } from '@/components/tool-step'
import { Badge } from '@/components/ui/badge'
import type {
  AddTransactionPart,
  ExtractTransactionPart,
  ExtractedBill,
  ImportFilePart,
  ImportProgress,
  StatementRead,
} from '@/lib/api'
import { formatDate, formatEur } from '@/lib/format'
import { cn } from '@/lib/utils'

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
    case 'extraction_review':
      return `${output.flagged} of ${bookings(output.rows_read)} in ${output.file} need your decision`
    case 'bill_split':
      return `${output.bill.merchant}: ${output.bill.items.length} line items to split a booking into`
    case 'bill_draft':
      return `${output.bill.merchant}: a receipt with no booking to match`
    case 'bill_matched':
      return `${output.bill?.merchant ?? output.file} is already booked`
    case 'already_imported':
      return `${output.file} was already imported`
    default:
      return 'Nothing was imported'
  }
}

/** What the reconciliation guard said, which is the one line that decides whether to trust
 *  the rows. Amber rather than red: the rows are shown, not thrown away. */
function Reconciled({ read }: { read: StatementRead }) {
  return (
    <p
      className={cn(
        'flex items-start gap-1.5 text-xs',
        read.reconciled === 'ok' ? 'text-muted-foreground' : 'text-amber-600 dark:text-amber-500',
      )}
    >
      <ScaleIcon aria-hidden="true" className="mt-0.5 size-3.5 shrink-0" />
      {read.reconciliation}
    </p>
  )
}

/** What the vision path read off a receipt, and whether its line items add up. */
function Bill({ bill }: { bill: ExtractedBill }) {
  return (
    <div className="space-y-2">
      <p className="text-sm">
        <span className="font-medium">{bill.merchant}</span>, {formatDate(bill.booked_on)},{' '}
        <span className="tabular-nums">{formatEur(-bill.total_cents)}</span>
      </p>
      {bill.items.length > 0 && (
        <ul className="space-y-0.5 text-xs">
          {bill.items.map((item, index) => (
            <li className="flex justify-between gap-3" key={`${item.description}-${index}`}>
              <span className="truncate text-muted-foreground">{item.description}</span>
              <span className="shrink-0 tabular-nums">{formatEur(-item.amount_cents)}</span>
            </li>
          ))}
        </ul>
      )}
      <p className={cn('text-xs', bill.verified ? 'text-muted-foreground' : 'text-amber-600 dark:text-amber-500')}>
        {bill.check}
      </p>
    </div>
  )
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
            {'reconciled' in part.output && <Reconciled read={part.output} />}
          </div>
        ) : part.output.status === 'extraction_review' ? (
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <Counts label="pages read" value={part.output.pages} />
              <Counts label="bookings read" value={part.output.rows_read} />
              <Counts label="need a decision" tone="review" value={part.output.flagged} />
              <Counts label="read as images" value={part.output.scanned_pages} />
            </div>
            <Reconciled read={part.output} />
            <p className="text-muted-foreground text-xs">
              {part.output.layout}. Nothing is imported until the question below is answered.
            </p>
          </div>
        ) : part.output.status === 'bill_split' ? (
          <div className="space-y-3">
            <Bill bill={part.output.bill} />
            <ChangesetProposal preview={part.output.changeset} />
          </div>
        ) : part.output.status === 'bill_draft' ? (
          <div className="space-y-3">
            <Bill bill={part.output.bill} />
            <p className="text-muted-foreground text-xs">
              No booking of this profile matches it, so it would be a new one. Confirm it below.
            </p>
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
