import type {
  AddTransactionOutput,
  AskUserInput,
  AskUserOutput,
  ChangesetField,
  ChangesetRow,
  ChangesetToolOutput,
  ChartToolOutput,
  ChatMessage,
  ExtractTransactionOutput,
  ImportFileOutput,
  LookupMerchantOutput,
  QueryToolOutput,
  ReviewBatchOutput,
  ReviewDuplicatesOutput,
  SetRuleOutput,
} from '@/lib/api'

/** The conversation as markdown, for the download button in the chat header.
 *
 * `ConversationDownload`'s own formatter reads `text` parts and nothing else, which for this app
 * would export the answers and silently drop every query, chart, changeset, card and import: the
 * whole audit trail, which is the only reason to export a FinQuery chat at all. So every part
 * the transcript draws writes a block here too, and the numbers in it are the ones the tools
 * came back with, exactly as on screen.
 */

type MessagePart = ChatMessage['parts'][number]

const ROLE: Record<string, string> = { user: 'You', assistant: 'FinQuery', system: 'System' }

const rows = (count: number) => (count === 1 ? '1 row' : `${count} rows`)

/** A block: a heading line, then any number of paragraphs and lists under it. */
const block = (...chunks: (string | null | undefined)[]) => chunks.filter(Boolean).join('\n\n')

const list = (lines: string[]) => (lines.length > 0 ? lines.map((line) => `- ${line}`).join('\n') : null)

const fence = (language: string, code: string) => `\`\`\`${language}\n${code.trim()}\n\`\`\``

function queryBlock(output: QueryToolOutput): string {
  return block(
    `**Query** · ${rows(output.row_count)}`,
    output.request,
    output.sql ? fence('sql', output.sql) : null,
    output.error ? `Refused: ${output.error}` : output.summary,
  )
}

function chartBlock(output: ChartToolOutput): string {
  return block(
    `**Chart** · ${output.title || output.request}`,
    output.plan,
    output.sql ? fence('sql', output.sql) : null,
    output.sql ? `Drawn from ${rows(output.row_count)}.` : null,
    list(output.notes),
    output.error ? `Not drawn: ${output.error}` : null,
  )
}

const answered = (answers: AskUserOutput['answers'], ref: string) => {
  const answer = answers.find((one) => one.ref === ref)
  return answer ? (answer.text ?? answer.value ?? null) : null
}

function askBlock(input: AskUserInput | undefined, output?: AskUserOutput): string {
  const answers = output?.answers ?? []
  const asked = input?.rows ?? []
  const lines = asked.map((row) => {
    const said = answered(answers, row.ref)
    return said ? `${row.label}: **${said}**` : row.label
  })
  // A card with no rows is one question with one answer, and its options are the answer set.
  if (asked.length === 0 && answers.length > 0) {
    lines.push(`Answer: **${answers[0].text ?? answers[0].value ?? ''}**`)
  }
  return block(
    `**Question card** · ${input?.title ?? 'A question'}`,
    input?.note,
    list(lines),
    output?.applied ? `Applied: ${output.applied}` : null,
    output ? null : '_Not answered yet._',
  )
}

const CHANGESET_STATUS: Record<ChangesetToolOutput['status'], string> = {
  proposed: 'waiting for you, nothing written',
  applied: 'applied',
  discarded: 'discarded',
  stale: 'out of date',
  superseded: 'replaced by a newer proposal',
}

const PREVIEW_ROWS = 10

const changed = (row: ChangesetRow, fields: ChangesetField[]) =>
  fields
    .map((field) => `${field} ${row.before?.[field] ?? '–'} → ${row.after?.[field] ?? '–'}`)
    .join(', ')

function changesetBlock(output: ChangesetToolOutput): string {
  const shown = output.rows.slice(0, PREVIEW_ROWS).map((row) => changed(row, output.fields))
  if (output.total > shown.length) shown.push(`and ${output.total - shown.length} more`)
  return block(
    `**Changeset** · ${output.title}`,
    `${output.kind}, ${CHANGESET_STATUS[output.status]}. ${output.summary}`,
    output.note,
    list(shown),
  )
}

function importBlock(output: ImportFileOutput): string {
  const head = `**Import** · ${'file' in output && output.file ? output.file : 'a file'}`
  if (output.status === 'imported') {
    return block(
      head,
      output.summary,
      list([
        `${output.rows_read} rows read, ${output.imported} imported into ${output.account}`,
        `${output.duplicates} duplicate candidates, ${output.categorized.needs_review} still needing review`,
        'reconciliation' in output ? `Reconciliation: ${output.reconciliation}` : null,
      ].filter((line): line is string => Boolean(line))),
    )
  }
  if ('message' in output && output.message) return block(head, output.message)
  if ('error' in output && output.error) return block(head, `${output.status}: ${output.error}`)
  return block(head, `Status: ${output.status.replaceAll('_', ' ')}.`)
}

function ruleBlock(output: SetRuleOutput): string {
  if (output.error) return block('**Rule**', output.error)
  const category = [output.category, output.subcategory].filter(Boolean).join(' · ')
  return block(
    '**Rule**',
    `Everything matching "${output.pattern}" is ${category}. ${output.updated ?? 0} bookings recategorized.`,
  )
}

function lookupBlock(output: LookupMerchantOutput): string {
  return block(
    `**Web lookup** · ${output.merchant || 'refused'}`,
    output.error ?? output.summary,
    list(output.sources.map((source) => `[${source.title}](${source.url})`)),
  )
}

function reviewBlock(output: ReviewBatchOutput): string {
  return block(
    `**Review queue** · ${output.pending_merchants} merchants still to place`,
    list(output.questions.map((question) => `${question.label} (${question.bookings} bookings)`)),
  )
}

function duplicatesBlock(output: ReviewDuplicatesOutput): string {
  return block(
    `**Duplicates** · ${output.found} found, ${output.pending} undecided`,
    output.message,
  )
}

function extractBlock(output: ExtractTransactionOutput): string {
  if (output.status !== 'preview') return block('**Booking preview**', output.error)
  return block(
    '**Booking preview**',
    list(output.drafts.map((draft) => `${draft.booked_on} ${draft.description} (${draft.amount_cents / 100} EUR)`)),
  )
}

function addedBlock(output: AddTransactionOutput): string {
  if (output.status === 'added') {
    const category = [output.category, output.subcategory].filter(Boolean).join(' · ')
    return block(
      '**Booking written**',
      `${output.booked_on} ${output.description} (${output.amount_cents / 100} EUR)${category ? `, ${category}` : ''}`,
    )
  }
  return block('**Booking**', 'message' in output ? output.message : output.error)
}

/** The one line a tool that never returned leaves behind, so a stopped turn reads as stopped. */
const unfinished = (type: string) => `_The ${type.slice('tool-'.length).replaceAll('_', ' ')} step has no result._`

function partToMarkdown(part: MessagePart): string | null {
  switch (part.type) {
    case 'text':
      return part.text.trim() || null
    case 'file':
      return `Attached: [${part.filename ?? 'attachment'}](${part.url})`
    case 'tool-query':
      return part.state === 'output-available' ? queryBlock(part.output) : unfinished(part.type)
    case 'tool-chart':
      return part.state === 'output-available' ? chartBlock(part.output) : unfinished(part.type)
    case 'tool-ask_user':
      // A card whose rows are still arriving is half a card; every later state carries all of it.
      if (part.state === 'input-streaming') return unfinished(part.type)
      return askBlock(part.input, part.state === 'output-available' ? part.output : undefined)
    case 'tool-propose_changeset':
    case 'tool-apply_simple_edit':
      return part.state === 'output-available' ? changesetBlock(part.output) : unfinished(part.type)
    case 'tool-import_file':
      return part.state === 'output-available' ? importBlock(part.output) : unfinished(part.type)
    case 'tool-set_rule':
      return part.state === 'output-available' ? ruleBlock(part.output) : unfinished(part.type)
    case 'tool-lookup_merchant':
      return part.state === 'output-available' ? lookupBlock(part.output) : unfinished(part.type)
    case 'tool-review_batch':
      return part.state === 'output-available' ? reviewBlock(part.output) : unfinished(part.type)
    case 'tool-review_duplicates':
      return part.state === 'output-available' ? duplicatesBlock(part.output) : unfinished(part.type)
    case 'tool-extract_transaction':
      return part.state === 'output-available' ? extractBlock(part.output) : unfinished(part.type)
    case 'tool-add_transaction':
      return part.state === 'output-available' ? addedBlock(part.output) : unfinished(part.type)
    case 'tool-remember':
      return part.state === 'output-available' ? `**Remembered** · ${part.output}` : unfinished(part.type)
    default:
      // The model's own thinking, the context reading, the follow-up chips and the progress
      // lines: scratch work and screen furniture, not part of what this chat established.
      return null
  }
}

export function messageToMarkdown(message: ChatMessage): string {
  const blocks = message.parts.map(partToMarkdown).filter((one): one is string => one !== null)
  if (blocks.length === 0 && message.metadata?.interrupted) {
    blocks.push('_This turn was interrupted before an answer was written._')
  }
  return [`## ${ROLE[message.role] ?? message.role}`, ...blocks].join('\n\n')
}

/** A file name a browser will take, from whatever the conversation happens to be called. */
export function transcriptFilename(title: string): string {
  const slug = title
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
    .slice(0, 60)
  return `finquery-${slug || 'conversation'}.md`
}
