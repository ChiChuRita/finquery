import { queryOptions } from '@tanstack/react-query'
import type { UIMessage } from 'ai'

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
}

/** Custom data parts the agent emits. The keys become `data-*` part types. */
export type ChatDataParts = {
  followups: { suggestions: string[] }
}

export type ChatMessage = UIMessage<ChatMetadata, ChatDataParts>

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
  interrupted: boolean
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: { 'content-type': 'application/json', ...init?.headers },
  })
  if (!response.ok) {
    throw new Error(await detailOf(response))
  }
  return response.status === 204 ? (undefined as T) : ((await response.json()) as T)
}

async function detailOf(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown }
    if (typeof body.detail === 'string') return body.detail
  } catch {
    // Not JSON, fall through to the status line.
  }
  return `${response.status} ${response.statusText}`
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

export const patchConversation = (id: string, patch: { title?: string; model_slot?: ModelSlot }) =>
  request<Conversation>(`/api/conversations/${id}`, { method: 'PATCH', body: JSON.stringify(patch) })

export const deleteConversation = (id: string) => request<void>(`/api/conversations/${id}`, { method: 'DELETE' })

export const stopConversation = (id: string) =>
  request<{ stopped: boolean }>(`/api/conversations/${id}/stop`, { method: 'POST' })

export const chatUrl = (id: string) => `/api/conversations/${id}/chat`
