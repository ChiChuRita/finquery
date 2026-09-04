import { infiniteQueryOptions, queryOptions } from '@tanstack/react-query'
import type { UIMessage } from 'ai'

export type ModelSlot = 'fast' | 'quality'

export const MODEL_SLOTS: { slot: ModelSlot; label: string; description: string }[] = [
  { slot: 'fast', label: 'Fast', description: 'Quick answers, lighter model' },
  { slot: 'quality', label: 'Quality', description: 'Slower, more careful reasoning' },
]

export type ChatMessage = UIMessage<{ interrupted?: boolean; thinking_seconds?: number }>

export interface Conversation {
  id: string
  title: string
  model_slot: ModelSlot
  created_at: string
  updated_at: string
}

export interface ConversationDetail extends Conversation {
  messages: ChatMessage[]
  interrupted: boolean
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
  return (await response.json()) as T
}

export const conversationsQuery = queryOptions({
  queryKey: ['conversations'],
  queryFn: () => request<Conversation[]>('/api/conversations'),
})

export const conversationQuery = (id: string) =>
  queryOptions({
    queryKey: ['conversations', id],
    queryFn: () => request<ConversationDetail>(`/api/conversations/${id}`),
  })

export const createConversation = (model_slot: ModelSlot) =>
  request<Conversation>('/api/conversations', { method: 'POST', body: JSON.stringify({ model_slot }) })

export const patchConversation = (id: string, model_slot: ModelSlot) =>
  request<Conversation>(`/api/conversations/${id}`, { method: 'PATCH', body: JSON.stringify({ model_slot }) })

export const stopConversation = (id: string) =>
  request<{ stopped: boolean }>(`/api/conversations/${id}/stop`, { method: 'POST' })

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

export function commitImport(file: File, mapping: CsvMapping, accountName: string) {
  const form = new FormData()
  form.set('file', file)
  form.set('mapping', JSON.stringify(mapping))
  form.set('account_name', accountName)
  return postForm<ImportRecord>('/api/imports', form)
}

export const importsQuery = queryOptions({
  queryKey: ['imports'],
  queryFn: () => request<ImportRecord[]>('/api/imports'),
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

function filterParams(filters: Filters): URLSearchParams {
  const params = new URLSearchParams()
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

export const transactionsQuery = (filters: Filters) =>
  infiniteQueryOptions({
    queryKey: ['transactions', 'list', filters] as const,
    queryFn: ({ pageParam }) => {
      const params = filterParams(filters)
      params.set('limit', String(PAGE_SIZE))
      params.set('offset', String(pageParam))
      return request<TransactionPage>(`/api/transactions?${params}`)
    },
    initialPageParam: 0,
    getNextPageParam: (last, pages) => {
      const loaded = pages.reduce((count, page) => count + page.rows.length, 0)
      return loaded < last.total ? loaded : undefined
    },
  })

export const accountsQuery = queryOptions({
  queryKey: ['accounts'],
  queryFn: () => request<AccountRef[]>('/api/accounts'),
})

export const categoriesQuery = queryOptions({
  queryKey: ['categories'],
  queryFn: () => request<CategoryRef[]>('/api/categories'),
})

export interface TransactionEdit {
  booked_on?: string
  description?: string
  amount_cents?: number
  category_id?: string | null
  subcategory_id?: string | null
  account_id?: string
}

export const patchTransaction = (id: string, edit: TransactionEdit) =>
  request<Transaction>(`/api/transactions/${id}`, { method: 'PATCH', body: JSON.stringify(edit) })

export interface NewTransaction {
  booked_on: string
  description: string
  amount_cents: number
  account_id: string
  category_id?: string | null
  subcategory_id?: string | null
}

export const createTransaction = (body: NewTransaction) =>
  request<Transaction>('/api/transactions', { method: 'POST', body: JSON.stringify(body) })

export interface SplitChild {
  id?: string
  description: string
  amount_cents: number
  category_id?: string | null
  subcategory_id?: string | null
}

export const splitsQuery = (id: string) =>
  queryOptions({
    queryKey: ['transactions', 'splits', id],
    queryFn: () => request<Transaction[]>(`/api/transactions/${id}/splits`),
  })

/** The whole set of legs at once: with an id it is edited, without one added, missing ones go. */
export const saveSplits = (id: string, children: SplitChild[]) =>
  request<Transaction[]>(`/api/transactions/${id}/splits`, { method: 'PUT', body: JSON.stringify({ children }) })

export const bulkRecategorize = (ids: string[], category_id: string | null, subcategory_id: string | null) =>
  request<{ updated: number }>('/api/transactions/bulk-recategorize', {
    method: 'POST',
    body: JSON.stringify({ ids, category_id, subcategory_id }),
  })

export const bulkDelete = (ids: string[]) =>
  request<{ deleted: number }>('/api/transactions/bulk-delete', { method: 'POST', body: JSON.stringify({ ids }) })
