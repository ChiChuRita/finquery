import { queryOptions } from '@tanstack/react-query'
import type { ToolUIPart, UIDataTypes, UIMessage } from 'ai'

export type ModelSlot = 'fast' | 'quality'

export const MODEL_SLOTS: { slot: ModelSlot; label: string; description: string }[] = [
  { slot: 'fast', label: 'Fast', description: 'Quick answers, lighter model' },
  { slot: 'quality', label: 'Quality', description: 'Slower, more careful reasoning' },
]

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

export type ChatTools = { query: { input: QueryToolInput; output: QueryToolOutput } }
export type QueryToolPart = ToolUIPart<ChatTools>

export type ChatMessage = UIMessage<
  { interrupted?: boolean; thinking_seconds?: number },
  UIDataTypes,
  ChatTools
>

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

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: { 'content-type': 'application/json', ...init?.headers },
  })
  if (!response.ok) {
    const detail = await response.text()
    throw new Error(`${response.status} ${response.statusText}: ${detail}`)
  }
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
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string } | null
    throw new Error(body?.detail ?? `${response.status} ${response.statusText}`)
  }
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
