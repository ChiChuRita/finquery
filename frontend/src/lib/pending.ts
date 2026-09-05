import type { FileUIPart } from 'ai'

/** What was typed, and attached, on the empty page before its conversation existed. */
export interface PendingMessage {
  text?: string
  files?: FileUIPart[]
}

// Consumed once by the conversation page right after it mounts. In memory rather than in local
// storage: an attachment is a data URL, which has no business being persisted twice.
const pending = new Map<string, PendingMessage>()

export const stashPendingPrompt = (conversationId: string, message: PendingMessage) =>
  pending.set(conversationId, message)

export function takePendingPrompt(conversationId: string): PendingMessage | undefined {
  const message = pending.get(conversationId)
  pending.delete(conversationId)
  return message
}

/** Whether a prompt is still waiting to be sent for this conversation, without consuming it.
 *
 * Read by the transcript on its first render: a conversation opened with something to send is a
 * view that streams its own turn, and must not also ask to reattach to it (ticket 33). */
export const hasPendingPrompt = (conversationId: string) => pending.has(conversationId)
