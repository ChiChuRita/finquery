// A prompt typed on the empty page before its conversation existed. Consumed once by the
// conversation page right after it mounts.
const pending = new Map<string, string>()

export const stashPendingPrompt = (conversationId: string, text: string) => pending.set(conversationId, text)

export function takePendingPrompt(conversationId: string): string | undefined {
  const text = pending.get(conversationId)
  pending.delete(conversationId)
  return text
}
