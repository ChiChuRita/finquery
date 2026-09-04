import type { ChatStatus } from 'ai'
import { useEffect } from 'react'

import {
  PromptInput,
  PromptInputBody,
  PromptInputFooter,
  PromptInputProvider,
  PromptInputSubmit,
  PromptInputTextarea,
  PromptInputTools,
  usePromptInputController,
  type PromptInputMessage,
} from '@/components/ai-elements/prompt-input'
import { ModelPicker } from '@/components/model-picker'
import type { ModelSlot } from '@/lib/api'
import { readDraft, writeDraft } from '@/lib/workspace'

export function Composer({
  status,
  onSubmit,
  onStop,
  slot,
  onSlotChange,
  autoFocus,
  draftId,
}: {
  status: ChatStatus
  onSubmit: (text: string) => void | Promise<void>
  onStop?: () => void
  slot: ModelSlot
  onSlotChange: (slot: ModelSlot) => void
  autoFocus?: boolean
  /** Conversation id whose unsent draft is kept in local storage. */
  draftId?: string
}) {
  const busy = status === 'submitted' || status === 'streaming'

  // Not awaited: the composer clears as soon as the message is on its way, not when the turn ends.
  const handleSubmit = (message: PromptInputMessage) => {
    const text = message.text.trim()
    if (!text || busy) return
    void onSubmit(text)
  }

  const input = (
    <PromptInput className="rounded-2xl shadow-xs" maxFiles={0} onSubmit={handleSubmit}>
      <PromptInputBody>
        <PromptInputTextarea
          autoFocus={autoFocus}
          className="min-h-14 text-base md:text-sm"
          placeholder="Ask about your spending..."
        />
      </PromptInputBody>
      <PromptInputFooter>
        <PromptInputTools>
          <ModelPicker onChange={onSlotChange} value={slot} />
        </PromptInputTools>
        <PromptInputSubmit className="rounded-full" onStop={onStop} status={status} />
      </PromptInputFooter>
    </PromptInput>
  )

  if (!draftId) return input
  return (
    <PromptInputProvider initialInput={readDraft(draftId)} key={draftId}>
      <DraftKeeper conversationId={draftId} />
      {input}
    </PromptInputProvider>
  )
}

/** Keeps what is typed but unsent, so switching tabs never loses a half-written question. */
function DraftKeeper({ conversationId }: { conversationId: string }) {
  const { textInput } = usePromptInputController()

  useEffect(() => {
    writeDraft(conversationId, textInput.value)
  }, [conversationId, textInput.value])

  return null
}
