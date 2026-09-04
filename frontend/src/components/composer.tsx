import type { ChatStatus } from 'ai'

import {
  PromptInput,
  PromptInputBody,
  PromptInputFooter,
  PromptInputSubmit,
  PromptInputTextarea,
  PromptInputTools,
  type PromptInputMessage,
} from '@/components/ai-elements/prompt-input'
import { ModelPicker } from '@/components/model-picker'
import type { ModelSlot } from '@/lib/api'

export function Composer({
  status,
  onSubmit,
  onStop,
  slot,
  onSlotChange,
  autoFocus,
}: {
  status: ChatStatus
  onSubmit: (text: string) => void | Promise<void>
  onStop?: () => void
  slot: ModelSlot
  onSlotChange: (slot: ModelSlot) => void
  autoFocus?: boolean
}) {
  const busy = status === 'submitted' || status === 'streaming'

  const handleSubmit = async (message: PromptInputMessage) => {
    const text = message.text.trim()
    if (!text || busy) return
    await onSubmit(text)
  }

  return (
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
}
