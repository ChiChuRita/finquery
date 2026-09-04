import { CheckIcon, ChevronDownIcon, GaugeIcon, SparklesIcon, ZapIcon } from 'lucide-react'
import { useState } from 'react'

import {
  ModelSelector,
  ModelSelectorContent,
  ModelSelectorGroup,
  ModelSelectorItem,
  ModelSelectorList,
  ModelSelectorTrigger,
} from '@/components/ai-elements/model-selector'
import { PromptInputButton } from '@/components/ai-elements/prompt-input'
import { MODEL_SLOTS, type ModelSlot } from '@/lib/api'
import { cn } from '@/lib/utils'

const ICONS: Record<ModelSlot, typeof ZapIcon> = { fast: ZapIcon, quality: SparklesIcon }

export function ModelPicker({
  value,
  onChange,
  disabled,
}: {
  value: ModelSlot
  onChange: (slot: ModelSlot) => void
  disabled?: boolean
}) {
  const [open, setOpen] = useState(false)
  const current = MODEL_SLOTS.find((m) => m.slot === value) ?? MODEL_SLOTS[0]
  const CurrentIcon = ICONS[current.slot]

  return (
    <ModelSelector onOpenChange={setOpen} open={open}>
      <ModelSelectorTrigger asChild>
        <PromptInputButton aria-label="Choose model" disabled={disabled} tooltip="Model for this conversation">
          <CurrentIcon className="size-4" />
          <span>{current.label}</span>
          <ChevronDownIcon className="size-3.5 opacity-60" />
        </PromptInputButton>
      </ModelSelectorTrigger>
      <ModelSelectorContent className="max-w-sm" defaultValue={value} title="Choose a model">
        <ModelSelectorList>
          {/* The same words the dialog answers to, so its heading and its name are one name. */}
          <ModelSelectorGroup heading="Choose a model">
            {MODEL_SLOTS.map((m) => {
              const Icon = ICONS[m.slot]
              const selected = m.slot === value
              return (
                <ModelSelectorItem
                  className="items-start gap-3 py-2.5"
                  key={m.slot}
                  onSelect={() => {
                    onChange(m.slot)
                    setOpen(false)
                  }}
                  value={m.slot}
                >
                  <span
                    className={cn(
                      'mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-md border',
                      selected ? 'border-primary/40 bg-primary/10 text-primary' : 'text-muted-foreground',
                    )}
                  >
                    <Icon className="size-4" />
                  </span>
                  <span className="flex min-w-0 flex-1 flex-col">
                    <span className="font-medium">{m.label}</span>
                    <span className="text-muted-foreground text-xs">{m.description}</span>
                  </span>
                  {selected ? <CheckIcon className="size-4 text-primary" /> : <GaugeIcon className="size-4 opacity-0" />}
                </ModelSelectorItem>
              )
            })}
          </ModelSelectorGroup>
        </ModelSelectorList>
      </ModelSelectorContent>
    </ModelSelector>
  )
}
