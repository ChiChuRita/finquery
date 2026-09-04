import { infiniteQueryOptions, queryOptions } from '@tanstack/react-query'
import type { ToolUIPart, UIMessage } from 'ai'

export type ModelSlot = 'fast' | 'quality'

export const MODEL_SLOTS: { slot: ModelSlot; label: string; description: string }[] = [
  { slot: 'fast', label: 'Fast', description: 'Quick answers, lighter model' },
  { slot: 'quality', label: 'Quality', description: 'Slower, more careful reasoning' },
]

export const slotLabel = (slot: ModelSlot | undefined) => MODEL_SLOTS.find((m) => m.slot === slot)?.label

export interface ChatMetadata {
  interrupted?: boolean
  thinking_seconds?: number
  model_slot?: ModelSlot
  /** The stored turn this message is, which is what a rating names (ticket 15). */
  turn_id?: string
}

/** What the context badge shows, emitted once per turn and stored on its assistant message. */
export interface ContextStats {
  /** Tokens the prompt and the answer of this turn took, so the badge can climb. */
  used: number
  budget: number
  slot: ModelSlot
  /** Memories selected into the prompt (at most five). */
  memories: number
  /** Turns the rolling summary stands in for. */
  summarized_turns: number
}

/** One line of progress from a running tool, streamed transient and never stored. */
export interface ImportProgress {
  stage: 'read' | 'mapping' | 'imported' | 'duplicates' | 'categorizing' | 'categorized'
  message: string
  counts: Record<string, number>
  /** The tool call this line belongs to, so it renders inside that step. */
  tool_call_id: string | null
}

/** Custom data parts the agent emits. The keys become `data-*` part types. */
export type ChatDataParts = {
  followups: { suggestions: string[] }
  /** What the turn used of the model's context: tokens, budget, memories, summary. */
  context: ContextStats
  /** Progress of an `import_file` call. Transient: live only, never in the transcript. */
  import_progress: ImportProgress
}

// The `query` tool: the request the sub-agent received, the SQL that ran and its rows.
export interface QueryToolInput {
  request: string
  hints?: string | null
}

export type QueryValue = string | number | boolean | null

export interface QueryToolOutput {
  request: string
  sql: string | null
  row_count: number
  columns: string[]
  rows: Record<string, QueryValue>[]
  summary: string
  error: string | null
}

// `ask_user`: the client-side tool. The input arrives as a tool part the browser renders as a
// Question card; the answer goes back with `addToolOutput` and resumes the run. Tickets 08, 10
// and 11 reuse the same contract for mapping confirmation, duplicates and review.
export interface AskOption {
  label: string
  value: string
}

export interface AskRow {
  ref: string
  label: string
  description?: string | null
  amount_cents?: number | null
  date?: string | null
  bookings?: number | null
  options?: AskOption[]
}

export interface AskUserInput {
  title: string
  note?: string | null
  rows?: AskRow[]
  options?: AskOption[]
  allow_free_text?: boolean
  /** What the server does with the answers before the model continues, when it does anything. */
  apply?: { kind: string } | null
}

export interface AskAnswer {
  ref: string
  value: string | null
  text: string | null
}

export interface AskUserOutput {
  answers: AskAnswer[]
  /** What the server applied for these answers before the model saw them, one line. */
  applied?: string | null
}

// `set_rule`: a category rule stored and applied to the whole profile.
export interface SetRuleInput {
  pattern: string
  category: string
  subcategory?: string | null
}

export interface SetRuleOutput {
  pattern: string
  category?: string
  subcategory?: string | null
  matched?: number
  updated?: number
  rule?: 'created' | 'updated'
  sample?: string[]
  error: string | null
}

// `remember`: one durable fact, stored for every conversation of the profile.
export interface RememberInput {
  text: string
  kind?: 'rule' | 'preference' | 'fact'
}

export interface ReviewQuestion {
  pattern: string
  label: string
  description: string
  date: string
  amount_cents: number
  bookings: number
  options: string[]
  guess: string | null
  confidence: number | null
}

export interface ReviewBatchOutput {
  pending_merchants: number
  questions: ReviewQuestion[]
}

// A booking an ingestion held aside because the profile may already have it. Nothing was
// inserted and nothing was dropped: the user answers Keep both or Remove.
export interface DuplicateCandidate {
  ref: string
  kind: 'exact' | 'near'
  booked_on: string
  amount_cents: number
  description: string
  counterparty: string | null
  existing_id: string | null
  existing_booked_on: string | null
  existing_description: string | null
}

export interface DuplicateCounts {
  found: number
  pending: number
  exact: number
  near: number
  kept: number
  removed: number
  /** Whether one answer may remove every exact duplicate: what a re-imported file looks like. */
  shortcut: boolean
}

/** `review_duplicates`: the next batch of candidates, ready as a Question card. */
export type ReviewDuplicatesOutput = DuplicateCounts & {
  candidates: DuplicateCandidate[]
  card: AskUserInput | null
  message: string
}

// The `chart` tool: the plan, the executed SQL and its rows, and the checked chart code.
export interface ChartToolInput {
  request: string
  hints?: string | null
}

export interface ChartToolOutput {
  request: string
  title: string
  shape: string
  plan: string
  sql: string | null
  row_count: number
  columns: string[]
  rows: Record<string, QueryValue>[]
  code: string | null
  notes: string[]
  summary: string
  error: string | null
}

// The changeset tools: `propose_changeset` hands back an inert proposal the user applies or
// discards, `apply_simple_edit` hands back a change that already happened, with an undo token.
export interface ChangesetToolInput {
  kind?: ChangesetKind
  title?: string
}

export type ChangesetToolOutput = Changeset & { undo_token?: string }

// `lookup_merchant`: the self-directed web lookup. Only present when the profile switched web
// lookup on, so a transcript from a profile with it off never carries this part.
export interface LookupSource {
  url: string
  title: string
}

export interface LookupMerchantOutput {
  /** The scrubbed merchant token, the only thing that left the machine. Empty when it refused. */
  merchant: string
  summary: string
  category: string | null
  subcategory: string | null
  confidence: number
  sources: LookupSource[]
  searches: number
  fetches: number
  /** True when the answer came from the profile's cache, so nothing left this time. */
  cached: boolean
  error: string | null
}

// `import_file`: one attached file through the ingestion pipeline. The status says what came of
// it, which is also what the tool step in the transcript renders.
export interface ImportCounts {
  by_rule: number
  by_dictionary: number
  by_model: number
  needs_review: number
  error: string | null
}

export type ImportFileOutput =
  | {
      status: 'imported'
      file: string
      account: string
      rows_read: number
      imported: number
      /** Bookings held aside as possible duplicates, none of them inserted or dropped. */
      duplicates: number
      exact_duplicates: number
      near_duplicates: number
      /** The first card to ask about them, when there are any. The merchants wait for it. */
      duplicate_card: AskUserInput | null
      unreadable_rows: number
      /** The one sentence about this import, counted on the server. */
      summary: string
      categorized: ImportCounts
      pending_merchants: number
      questions: ReviewQuestion[]
      instruction?: string
    }
  | {
      status: 'confirm_mapping'
      file: string
      note: string
      mapping: CsvMapping
      card: AskUserInput
      instruction: string
    }
  | { status: 'extraction_not_ready' | 'already_imported'; file: string; message: string }
  | { status: 'no_such_file'; error: string; attached_files: string[] }
  | { status: 'unreadable' | 'mapping_failed'; file?: string; error: string }

// `extract_transaction`: what the user typed or pasted, as drafts to confirm.
export interface TransactionDraft {
  ref: string
  booked_on: string
  amount_cents: number
  description: string
  counterparty: string | null
  account: string
}

export type ExtractTransactionOutput =
  | { status: 'preview'; drafts: TransactionDraft[]; problems: string[]; card: AskUserInput; instruction: string }
  | { status: 'nothing_found'; error: string; problems: string[] }
  | { status: 'unavailable' | 'failed'; error: string }

// `add_transaction`: one confirmed draft, written and categorized.
export type AddTransactionOutput =
  | {
      status: 'added'
      ref: string
      transaction_id: string
      booked_on: string
      amount_cents: number
      description: string
      account: string
      title: string | null
      category: string | null
      subcategory: string | null
      needs_review: boolean
      error: string | null
    }
  | { status: 'already_added'; ref: string; description: string; message: string }
  | { status: 'no_such_draft'; ref: string; error: string }

/** The tools the agent may call. The keys become `tool-*` part types. */
export type ChatTools = {
  query: { input: QueryToolInput; output: QueryToolOutput }
  chart: { input: ChartToolInput; output: ChartToolOutput }
  ask_user: { input: AskUserInput; output: AskUserOutput }
  set_rule: { input: SetRuleInput; output: SetRuleOutput }
  remember: { input: RememberInput; output: string }
  review_batch: { input: { limit?: number }; output: ReviewBatchOutput }
  review_duplicates: { input: { limit?: number }; output: ReviewDuplicatesOutput }
  propose_changeset: { input: ChangesetToolInput; output: ChangesetToolOutput }
  apply_simple_edit: { input: ChangesetToolInput; output: ChangesetToolOutput }
  lookup_merchant: { input: { merchant: string }; output: LookupMerchantOutput }
  import_file: {
    input: { file_name: string; account_name?: string | null; confirmed?: boolean }
    output: ImportFileOutput
  }
  extract_transaction: { input: { text: string }; output: ExtractTransactionOutput }
  add_transaction: { input: { ref: string }; output: AddTransactionOutput }
}
export type QueryToolPart = ToolUIPart<{ query: ChatTools['query'] }>
export type AskUserPart = ToolUIPart<{ ask_user: ChatTools['ask_user'] }>
export type SetRulePart = ToolUIPart<{ set_rule: ChatTools['set_rule'] }>
export type RememberPart = ToolUIPart<{ remember: ChatTools['remember'] }>
export type ReviewBatchPart = ToolUIPart<{ review_batch: ChatTools['review_batch'] }>
export type ReviewDuplicatesPart = ToolUIPart<{ review_duplicates: ChatTools['review_duplicates'] }>
// One part type for both writing tools: the card renders the same shape either way.
export type ChangesetToolPart = ToolUIPart<{
  propose_changeset: ChatTools['propose_changeset']
  apply_simple_edit: ChatTools['apply_simple_edit']
}>
export type ChartToolPart = ToolUIPart<{ chart: ChatTools['chart'] }>
export type LookupMerchantPart = ToolUIPart<{ lookup_merchant: ChatTools['lookup_merchant'] }>
export type ImportFilePart = ToolUIPart<{ import_file: ChatTools['import_file'] }>
export type ExtractTransactionPart = ToolUIPart<{ extract_transaction: ChatTools['extract_transaction'] }>
export type AddTransactionPart = ToolUIPart<{ add_transaction: ChatTools['add_transaction'] }>

export type ChatMessage = UIMessage<ChatMetadata, ChatDataParts, ChatTools>

export interface Profile {
  id: string
  name: string
  created_at: string
}

export interface Conversation {
  id: string
  profile_id: string
  title: string
  model_slot: ModelSlot
  created_at: string
  updated_at: string
}

export interface ConversationDetail extends Conversation {
  messages: ChatMessage[]
  /** The thumbs and picks already given in this chat, so a reload shows them again. */
  ratings: TurnRating[]
  interrupted: boolean
  /** The rolling summary of the turns before the divider, editable in the transcript. */
  summary: string | null
  summarized_turns: number
  /** How many of `messages` the summary replaces, which is where the divider goes. */
  summarized_messages: number
}

// Preference records: what a thumb, a chart pick or an answer A/B left behind.

export type PreferenceKind = 'answer' | 'chart'
export type PreferenceRating = 'up' | 'down' | 'pick'

export interface TurnRating {
  turn_id: string
  /** The tool call id of the chart it is about, or null for the answer of the turn. */
  target: string | null
  kind: PreferenceKind
  rating: PreferenceRating
}

export interface PreferenceRecord extends TurnRating {
  id: string
  profile_id: string
  conversation_id: string | null
  prompt: string
  /** True when both sides are stored, which is what a DPO export can use. */
  paired: boolean
  model_slot: ModelSlot
  created_at: string
}

/** The half of a pair that was never a turn: a second answer, or a regenerated chart. */
export interface PairCandidate {
  text?: string
  tools?: unknown[]
  code?: string | null
  shape?: string
  title?: string
}

export interface AlternativeAnswer {
  text: string
  tools: unknown[]
  model_slot: ModelSlot
  temperature: number
}

// The API refuses a write with a readable `detail`; FastAPI's own body validation answers with
// a list of errors instead. Both become one sentence a cell can show.
async function problem(response: Response): Promise<string> {
  const body = (await response.json().catch(() => null)) as { detail?: unknown } | null
  const detail = body?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return String((detail[0] as { msg?: string } | undefined)?.msg ?? 'That value is not usable.')
  return `${response.status} ${response.statusText}`
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: { 'content-type': 'application/json', ...init?.headers },
  })
  if (!response.ok) throw new Error(await problem(response))
  // A delete answers 204 with no body.
  return response.status === 204 ? (undefined as T) : ((await response.json()) as T)
}

export const profilesQuery = queryOptions({
  queryKey: ['profiles'],
  queryFn: () => request<Profile[]>('/api/profiles'),
})

export const createProfile = (name: string) =>
  request<Profile>('/api/profiles', { method: 'POST', body: JSON.stringify({ name }) })

export const renameProfile = (id: string, name: string) =>
  request<Profile>(`/api/profiles/${id}`, { method: 'PATCH', body: JSON.stringify({ name }) })

export const deleteProfile = (id: string) => request<void>(`/api/profiles/${id}`, { method: 'DELETE' })

export const conversationsQuery = (profileId: string | undefined) =>
  queryOptions({
    queryKey: ['conversations', { profileId }],
    queryFn: () => request<Conversation[]>(`/api/conversations?profile_id=${profileId}`),
    enabled: profileId !== undefined,
  })

export const conversationQuery = (id: string) =>
  queryOptions({
    queryKey: ['conversation', id],
    queryFn: () => request<ConversationDetail>(`/api/conversations/${id}`),
  })

export const createConversation = (profile_id: string, model_slot: ModelSlot) =>
  request<Conversation>('/api/conversations', { method: 'POST', body: JSON.stringify({ profile_id, model_slot }) })

export const patchConversation = (id: string, patch: { title?: string; model_slot?: ModelSlot; summary?: string }) =>
  request<Conversation>(`/api/conversations/${id}`, { method: 'PATCH', body: JSON.stringify(patch) })

export const deleteConversation = (id: string) => request<void>(`/api/conversations/${id}`, { method: 'DELETE' })

export const stopConversation = (id: string) =>
  request<{ stopped: boolean }>(`/api/conversations/${id}/stop`, { method: 'POST' })

// Memory: durable facts shared by every conversation of the profile.

export type MemoryKind = 'rule' | 'preference' | 'fact'
export type MemorySource = 'explicit' | 'distilled'

export interface Memory {
  id: string
  profile_id: string
  text: string
  kind: MemoryKind
  source: MemorySource
  /** The conversation it was established in, null once that conversation is deleted. */
  created_from: string | null
  created_at: string
  updated_at: string
}

export const memoriesQuery = (profileId: string | undefined) =>
  queryOptions({
    queryKey: ['memories', { profileId }],
    queryFn: () => request<Memory[]>(`/api/memories?profile_id=${profileId}`),
    enabled: profileId !== undefined,
  })

export const patchMemory = (id: string, patch: { text?: string; kind?: MemoryKind }) =>
  request<Memory>(`/api/memories/${id}`, { method: 'PATCH', body: JSON.stringify(patch) })

export const deleteMemory = (id: string) => request<void>(`/api/memories/${id}`, { method: 'DELETE' })

// Per-profile settings, and the log of everything that ever left the machine.

export interface ProfileSettings {
  profile_id: string
  web_lookup_enabled: boolean
}

export interface OutboundEntry {
  id: string
  kind: 'search' | 'fetch'
  /** Literally what was sent: the search query or the URL. */
  target: string
  merchant_token: string
  /** `sent` while it is in flight, then `ok` or a short reason it failed. */
  status: string
  created_at: string
}

export const settingsQuery = (profileId: string | undefined) =>
  queryOptions({
    queryKey: ['settings', { profileId }],
    queryFn: () => request<ProfileSettings>(`/api/settings?profile_id=${profileId}`),
    enabled: profileId !== undefined,
  })

export const patchSettings = (profileId: string, patch: { web_lookup_enabled?: boolean }) =>
  request<ProfileSettings>('/api/settings', {
    method: 'PATCH',
    body: JSON.stringify({ profile_id: profileId, ...patch }),
  })

export const outboundLogQuery = (profileId: string | undefined) =>
  queryOptions({
    queryKey: ['outbound-log', { profileId }],
    queryFn: () => request<OutboundEntry[]>(`/api/outbound-log?profile_id=${profileId}`),
    enabled: profileId !== undefined,
  })

export type FileState = 'missing' | 'verifying' | 'downloading' | 'ready' | 'error'

export interface ModelFile {
  kind: string
  filename: string
  size: number
  downloaded: number
  state: FileState
  source: string | null
  error: string | null
}

export interface SlotModel {
  slot: ModelSlot
  name: string
  ready: boolean
  loaded: boolean
  load_seconds: number | null
  n_ctx: number | null
  files: ModelFile[]
}

export interface Models {
  provider: string
  models: SlotModel[]
  adapters: { name: string; path: string; present: boolean }[]
  downloading: boolean
}

export interface SanityCheck {
  name: string
  ok: boolean
  detail: string
  seconds: number
  tokens_per_second: number | null
}

export interface SanityReport {
  slot: ModelSlot
  model: string
  ok: boolean
  load_seconds: number | null
  error: string | null
  checks: SanityCheck[]
  adapters: { name: string; attached: boolean; note: string | null }[]
}

// Also the download progress endpoint: poll it while `downloading` is true.
export const modelsQuery = queryOptions({
  queryKey: ['models'],
  queryFn: () => request<Models>('/api/models'),
  refetchInterval: (query) => (query.state.data?.downloading ? 700 : false),
})

export const startModelDownload = () => request<Models>('/api/models/download', { method: 'POST' })

export const runSanityCheck = () =>
  request<{ ok: boolean; reports: SanityReport[] }>('/api/models/check', { method: 'POST' })

export const chatUrl = (id: string) => `/api/conversations/${id}/chat`

// Import

export const DATE_FORMATS = ['DD.MM.YYYY', 'DD.MM.YY', 'YYYY-MM-DD', 'DD/MM/YYYY', 'MM/DD/YYYY'] as const
export type DateFormat = (typeof DATE_FORMATS)[number]

export interface CsvMapping {
  date_column: string
  amount_column?: string | null
  debit_column?: string | null
  credit_column?: string | null
  description_column?: string | null
  counterparty_column?: string | null
  date_format: DateFormat
  decimal_separator: 'comma' | 'dot'
}

export interface PreviewRow {
  booked_on: string
  amount_cents: number
  description: string
  counterparty: string | null
}

export interface ImportPreview {
  file_name: string
  encoding: string
  delimiter: string
  header: string[]
  row_count: number
  skipped_count: number
  preset: string | null
  preset_label: string | null
  mapping: CsvMapping
  account_name: string
  note: string
  mapping_source: 'preset' | 'model' | 'user'
  rows: PreviewRow[]
  issues: string[]
}

export interface ImportRecord {
  id: string
  file_name: string
  kind: string
  preset: string | null
  account_name: string
  row_count: number
  imported_count: number
  duplicate_count: number
  duplicates_kept: number
  duplicates_removed: number
  skipped_count: number
  reconciliation: string | null
  created_at: string
}

async function postForm<T>(url: string, form: FormData): Promise<T> {
  const response = await fetch(url, { method: 'POST', body: form })
  if (!response.ok) throw new Error(await problem(response))
  return (await response.json()) as T
}

// The file is posted again with every mapping change, so the server keeps no upload state.
export function previewImport(file: File, mapping?: CsvMapping, accountName?: string) {
  const form = new FormData()
  form.set('file', file)
  if (mapping) form.set('mapping', JSON.stringify(mapping))
  if (accountName) form.set('account_name', accountName)
  return postForm<ImportPreview>('/api/imports/preview', form)
}

export function commitImport(profileId: string, file: File, mapping: CsvMapping, accountName: string) {
  const form = new FormData()
  form.set('profile_id', profileId)
  form.set('file', file)
  form.set('mapping', JSON.stringify(mapping))
  form.set('account_name', accountName)
  return postForm<ImportRecord>('/api/imports', form)
}

// The duplicate candidates one import held aside, and the decision about them.

export type ImportDuplicates = DuplicateCounts & {
  import_id: string
  file_name: string
  account_name: string
  candidates: DuplicateCandidate[]
}

export interface DuplicateDecided {
  kept: number
  removed: number
  remaining: number
  needs_review: number
  /** The import summary sentence again, now saying how many were kept and removed. */
  summary: string
  error: string | null
}

export const importDuplicates = (importId: string, profileId: string) =>
  request<ImportDuplicates>(`/api/imports/${importId}/duplicates?profile_id=${profileId}`)

export const decideDuplicates = (
  importId: string,
  profileId: string,
  decisions: { ref: string; decision: 'keep' | 'remove' }[],
  removeAllExact = false,
) =>
  request<DuplicateDecided>(`/api/imports/${importId}/duplicates`, {
    method: 'POST',
    body: JSON.stringify({ profile_id: profileId, decisions, remove_all_exact: removeAllExact }),
  })

// Categorization of a finished import, and the conversation that asks about what is left.

export interface CategorizeReport {
  import_id: string
  rows: number
  by_rule: number
  by_dictionary: number
  by_lookup: number
  by_model: number
  needs_review: number
  merchants: number
  model_calls: number
  /** Merchants looked up on the web, zero unless the profile switched web lookup on. */
  lookups: number
  /** Merchants it refused to look up because nothing was safe to send. */
  lookups_refused: number
  uncertain: ReviewQuestion[]
  error: string | null
}

export interface ReviewConversation {
  conversation_id: string
  title: string
  questions: number
  pending_merchants: number
}

export const categorizeImport = (importId: string, profileId: string) =>
  request<CategorizeReport>(`/api/imports/${importId}/categorize`, {
    method: 'POST',
    body: JSON.stringify({ profile_id: profileId }),
  })

export const openReviewConversation = (importId: string, profileId: string, model_slot: ModelSlot = 'fast') =>
  request<ReviewConversation>(`/api/imports/${importId}/review-conversation`, {
    method: 'POST',
    body: JSON.stringify({ profile_id: profileId, model_slot }),
  })

// Everything below the profile boundary is asked for by id, the same as conversations.
export const importsQuery = (profileId: string | undefined) =>
  queryOptions({
    queryKey: ['imports', { profileId }],
    queryFn: () => request<ImportRecord[]>(`/api/imports?profile_id=${profileId}`),
    enabled: profileId !== undefined,
  })

// Transactions

export interface Transaction {
  id: string
  booked_on: string
  description: string
  counterparty: string | null
  title: string | null
  amount_cents: number
  category_id: string | null
  category: string | null
  subcategory_id: string | null
  subcategory: string | null
  account_id: string
  account: string
  source: string
  parent_id: string | null
  split_count: number
}

export interface TransactionPage {
  total: number
  rows: Transaction[]
}

export interface SubcategoryRef {
  id: string
  name: string
}

export interface CategoryRef extends SubcategoryRef {
  subcategories: SubcategoryRef[]
}

export interface AccountRef {
  id: string
  name: string
}

export interface Filters {
  q: string
  date_from: string
  date_to: string
  category_id: string
  account_id: string
  needs_review: boolean
}

export const NO_FILTERS: Filters = {
  q: '',
  date_from: '',
  date_to: '',
  category_id: '',
  account_id: '',
  needs_review: false,
}

export const hasFilters = (filters: Filters) =>
  Object.entries(filters).some(([key, value]) => value !== NO_FILTERS[key as keyof Filters])

/** One request's worth of rows. The table virtualizes and asks for the next chunk as it scrolls. */
export const PAGE_SIZE = 500

function filterParams(profileId: string, filters: Filters): URLSearchParams {
  const params = new URLSearchParams({ profile_id: profileId })
  // The page lists split parents with a badge and edits their children in the expanded row.
  params.set('include_parents', 'true')
  if (filters.q.trim()) params.set('q', filters.q.trim())
  if (filters.date_from) params.set('date_from', filters.date_from)
  if (filters.date_to) params.set('date_to', filters.date_to)
  if (filters.category_id) params.set('category_id', filters.category_id)
  if (filters.account_id) params.set('account_id', filters.account_id)
  if (filters.needs_review) params.set('needs_review', 'true')
  return params
}

export const transactionsQuery = (profileId: string | undefined, filters: Filters) =>
  infiniteQueryOptions({
    queryKey: ['transactions', 'list', { profileId }, filters] as const,
    queryFn: ({ pageParam }) => {
      const params = filterParams(profileId as string, filters)
      params.set('limit', String(PAGE_SIZE))
      params.set('offset', String(pageParam))
      return request<TransactionPage>(`/api/transactions?${params}`)
    },
    initialPageParam: 0,
    getNextPageParam: (last, pages) => {
      const loaded = pages.reduce((count, page) => count + page.rows.length, 0)
      return loaded < last.total ? loaded : undefined
    },
    enabled: profileId !== undefined,
  })

/** How many bookings the profile holds, asked for with one row: the empty state offers questions
 *  about spending only once there is spending to ask about. */
export const transactionCountQuery = (profileId: string | undefined) =>
  queryOptions({
    queryKey: ['transactions', 'count', { profileId }],
    queryFn: async () => {
      const page = await request<TransactionPage>(`/api/transactions?profile_id=${profileId}&limit=1`)
      return page.total
    },
    enabled: profileId !== undefined,
  })

export const accountsQuery = (profileId: string | undefined) =>
  queryOptions({
    queryKey: ['accounts', { profileId }],
    queryFn: () => request<AccountRef[]>(`/api/accounts?profile_id=${profileId}`),
    enabled: profileId !== undefined,
  })

export const categoriesQuery = (profileId: string | undefined) =>
  queryOptions({
    queryKey: ['categories', { profileId }],
    queryFn: () => request<CategoryRef[]>(`/api/categories?profile_id=${profileId}`),
    enabled: profileId !== undefined,
  })

export interface TransactionEdit {
  booked_on?: string
  description?: string
  amount_cents?: number
  category_id?: string | null
  subcategory_id?: string | null
  account_id?: string
}

// A write carries the profile in its body: it is who may edit the row, not what to write.
export const patchTransaction = (profileId: string, id: string, edit: TransactionEdit) =>
  request<Transaction>(`/api/transactions/${id}`, {
    method: 'PATCH',
    body: JSON.stringify({ profile_id: profileId, ...edit }),
  })

export interface NewTransaction {
  booked_on: string
  description: string
  amount_cents: number
  account_id: string
  category_id?: string | null
  subcategory_id?: string | null
}

export const createTransaction = (profileId: string, body: NewTransaction) =>
  request<Transaction>('/api/transactions', {
    method: 'POST',
    body: JSON.stringify({ profile_id: profileId, ...body }),
  })

export interface SplitChild {
  id?: string
  description: string
  amount_cents: number
  category_id?: string | null
  subcategory_id?: string | null
}

export const splitsQuery = (profileId: string | undefined, id: string) =>
  queryOptions({
    queryKey: ['transactions', 'splits', { profileId }, id],
    queryFn: () => request<Transaction[]>(`/api/transactions/${id}/splits?profile_id=${profileId}`),
    enabled: profileId !== undefined,
  })

/** The whole set of legs at once: with an id it is edited, without one added, missing ones go. */
export const saveSplits = (profileId: string, id: string, children: SplitChild[]) =>
  request<Transaction[]>(`/api/transactions/${id}/splits`, {
    method: 'PUT',
    body: JSON.stringify({ profile_id: profileId, children }),
  })

export const bulkRecategorize = (
  profileId: string,
  ids: string[],
  category_id: string | null,
  subcategory_id: string | null,
) =>
  request<{ updated: number }>('/api/transactions/bulk-recategorize', {
    method: 'POST',
    body: JSON.stringify({ profile_id: profileId, ids, category_id, subcategory_id }),
  })

export const bulkDelete = (profileId: string, ids: string[]) =>
  request<{ deleted: number }>('/api/transactions/bulk-delete', {
    method: 'POST',
    body: JSON.stringify({ profile_id: profileId, ids }),
  })

// Changesets: a proposal with the exact rows it would touch, inert until it is applied.

export type ChangesetKind = 'recategorize' | 'split' | 'edit' | 'delete' | 'taxonomy'
export type ChangesetStatus = 'proposed' | 'applied' | 'discarded' | 'stale' | 'superseded'
export type ChangesetField = 'date' | 'description' | 'amount' | 'category' | 'subcategory'

/** Display strings straight from the preview, so the card never recomputes a number. */
export type ChangesetValues = Partial<Record<ChangesetField, string | null>>

export interface ChangesetRow {
  /** The transaction, or null for a row the changeset creates (a leg of a split). */
  id: string | null
  before: ChangesetValues | null
  /** Null when the row goes away: deleted, or replaced by the legs of a split. */
  after: ChangesetValues | null
}

export interface Changeset {
  id: string
  profile_id: string
  conversation_id: string | null
  kind: ChangesetKind
  title: string
  status: ChangesetStatus
  summary: string
  note: string | null
  /** Every affected row, even when `rows` below is only the first page of them. */
  total: number
  fields: ChangesetField[]
  rows: ChangesetRow[]
  undoable: boolean
  created_at: string
  applied_at: string | null
}

/** The card's own source of truth: the tool output shows the preview, the server the status. */
export const changesetQuery = (profileId: string | undefined, id: string) =>
  queryOptions({
    queryKey: ['changeset', { profileId }, id],
    queryFn: () => request<Changeset>(`/api/changesets/${id}?profile_id=${profileId}`),
    enabled: profileId !== undefined,
  })

export type TaxonomyOperation = 'add' | 'rename' | 'merge' | 'delete'

export interface TaxonomyChange {
  operation: TaxonomyOperation
  category: string
  subcategory?: string | null
  new_name?: string | null
  into?: string | null
}

/** The Settings editor proposes the same changeset the assistant would, then applies it. */
export const proposeTaxonomyChange = (profileId: string, title: string, taxonomy: TaxonomyChange) =>
  request<Changeset>('/api/changesets', {
    method: 'POST',
    body: JSON.stringify({ profile_id: profileId, intent: { kind: 'taxonomy', title, taxonomy } }),
  })

const changesetAction = (action: string) => (profileId: string, id: string) =>
  request<Changeset>(`/api/changesets/${id}/${action}`, {
    method: 'POST',
    body: JSON.stringify({ profile_id: profileId }),
  })

export const applyChangeset = changesetAction('apply')
export const discardChangeset = changesetAction('discard')
export const undoChangeset = changesetAction('undo')

// Preferences: rating, the two reruns behind a pair, the pick and the export.

export const preferencesQuery = (profileId: string | undefined) =>
  queryOptions({
    queryKey: ['preferences', { profileId }],
    queryFn: () => request<PreferenceRecord[]>(`/api/preferences?profile_id=${profileId}`),
    enabled: profileId !== undefined,
  })

/** A plain link, so the browser saves the JSONL as a file instead of the app buffering it. */
export const preferencesExportUrl = (profileId: string) => `/api/preferences/export?profile_id=${profileId}`

export const ratePreference = (
  profileId: string,
  body: { turn_id: string; target?: string | null; rating: 'up' | 'down' },
) =>
  request<PreferenceRecord>('/api/preferences/rating', {
    method: 'POST',
    body: JSON.stringify({ profile_id: profileId, ...body }),
  })

export const storePreferencePair = (
  profileId: string,
  body: { turn_id: string; target?: string | null; picked: 'original' | 'candidate'; candidate: PairCandidate },
) =>
  request<PreferenceRecord>('/api/preferences/pair', {
    method: 'POST',
    body: JSON.stringify({ profile_id: profileId, ...body }),
  })

/** Draw the same chart request a second time. No chat turn, so the transcript does not grow. */
export const chartAlternative = (profileId: string, turn_id: string, tool_call_id: string) =>
  request<ChartToolOutput>('/api/preferences/chart-alternative', {
    method: 'POST',
    body: JSON.stringify({ profile_id: profileId, turn_id, tool_call_id }),
  })

/** Answer the same message a second time, hotter, with only the read-only query tool. */
export const answerAlternative = (profileId: string, turn_id: string) =>
  request<AlternativeAnswer>('/api/preferences/answer-alternative', {
    method: 'POST',
    body: JSON.stringify({ profile_id: profileId, turn_id }),
  })
