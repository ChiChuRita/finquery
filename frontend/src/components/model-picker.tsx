import { CheckIcon, ChevronDownIcon, CloudIcon, GaugeIcon, HardDriveIcon, Loader2Icon } from 'lucide-react'
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
import type { CatalogEntry, ModelKey } from '@/lib/api'
import { useCatalog } from '@/lib/catalog'
import { cn } from '@/lib/utils'

/** Where the model runs, which is the one thing the two halves of a pair differ in. */
const ICONS = { local: HardDriveIcon, openrouter: CloudIcon }

const WHERE = { local: 'On this machine', openrouter: 'Through OpenRouter' }

/** The line under an entry: why it cannot answer, else where it runs. */
function entryNote(entry: CatalogEntry): string {
  if (!entry.available) return entry.reason ?? 'Not available'
  if (entry.swapping) return 'Loading into the local seat'
  if (entry.loaded) return `${WHERE[entry.provider]}, loaded`
  return WHERE[entry.provider]
}

export function ModelPicker({
  value,
  onChange,
  disabled,
}: {
  value: ModelKey | undefined
  onChange: (key: ModelKey) => void
  disabled?: boolean
}) {
  const [open, setOpen] = useState(false)
  const { entries, entry, label } = useCatalog()
  const current = entry(value)
  const CurrentIcon = current ? ICONS[current.provider] : GaugeIcon

  return (
    <ModelSelector onOpenChange={setOpen} open={open}>
      <ModelSelectorTrigger asChild>
        <PromptInputButton aria-label="Choose model" disabled={disabled} tooltip="Model for this conversation">
          <CurrentIcon className="size-4" />
          <span>{label(value) ?? 'Model'}</span>
          <ChevronDownIcon className="size-3.5 opacity-60" />
        </PromptInputButton>
      </ModelSelectorTrigger>
      <ModelSelectorContent className="max-w-sm" defaultValue={value} title="Choose a model">
        <ModelSelectorList>
          {/* The same words the dialog answers to, so its heading and its name are one name. */}
          <ModelSelectorGroup heading="Choose a model">
            {entries.map((model) => {
              const Icon = ICONS[model.provider]
              const selected = model.key === value
              return (
                <ModelSelectorItem
                  className={cn('items-start gap-3 py-2.5', !model.available && 'opacity-60')}
                  disabled={!model.available}
                  key={model.key}
                  onSelect={() => {
                    // An entry that cannot answer is shown with the reason rather than hidden,
                    // and choosing it would only move the failure to the next turn.
                    if (!model.available) return
                    onChange(model.key)
                    setOpen(false)
                  }}
                  value={model.key}
                >
                  <span
                    className={cn(
                      'mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-md border',
                      selected ? 'border-primary/40 bg-primary/10 text-primary' : 'text-muted-foreground',
                    )}
                  >
                    {model.swapping ? <Loader2Icon className="size-4 animate-spin" /> : <Icon className="size-4" />}
                  </span>
                  <span className="flex min-w-0 flex-1 flex-col">
                    <span className="font-medium">{model.label}</span>
                    <span className="text-muted-foreground text-xs">{entryNote(model)}</span>
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
