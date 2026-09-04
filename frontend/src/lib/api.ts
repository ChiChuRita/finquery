import { queryOptions } from '@tanstack/react-query'
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
