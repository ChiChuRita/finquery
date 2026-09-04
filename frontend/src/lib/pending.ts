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
