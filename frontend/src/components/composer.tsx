import type { ChatStatus, FileUIPart } from 'ai'
import { FileTextIcon, ImageIcon, PaperclipIcon, XIcon } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'

import {
  PromptInput,
  PromptInputBody,
  PromptInputButton,
  PromptInputFooter,
  PromptInputProvider,
  PromptInputSubmit,
  PromptInputTextarea,
  PromptInputTools,
  usePromptInputAttachments,
  usePromptInputController,
  type PromptInputMessage,
} from '@/components/ai-elements/prompt-input'
import { ModelPicker } from '@/components/model-picker'
import type { ModelSlot } from '@/lib/api'
import { readDraft, writeDraft } from '@/lib/workspace'

/** What the server stores (see `finquery.attachments`): a bank CSV, a statement PDF, a bill photo.
 *  The extensions are for the file dialog, the media types are what the drop is checked against. */
const ACCEPT =
  '.csv,.tsv,.txt,.pdf,text/csv,text/plain,text/tab-separated-values,application/csv,application/vnd.ms-excel,application/pdf,image/*'
const MAX_FILES = 5
const MAX_FILE_BYTES = 20 * 1024 * 1024

/** What the composer says when it will not take a file, in this app's own words.
 *
 * The library writes for many files at once ("All files exceed the maximum size."), where the
 * case here is nearly always one file that has to be swapped for another one. The sentences
 * match what the server answers for the same three refusals (`finquery.attachments`).
 */
const REJECTED: Record<string, string> = {
  accept: 'FinQuery reads a CSV export, a statement PDF or a photo. That file is none of the three.',
  max_file_size: `A file has to be under ${MAX_FILE_BYTES / (1024 * 1024)} MB. Export a shorter date range from your bank and attach that.`,
  max_files: `One message carries at most ${MAX_FILES} files. Send these and attach the rest after.`,
}

export function Composer({
  status,
  onSubmit,
  onStop,
  slot,
  onSlotChange,
  autoFocus,
  draftId,
  focusToken = 0,
}: {
  status: ChatStatus
  onSubmit: (text: string, files: FileUIPart[]) => void | Promise<void>
  onStop?: () => void
  slot: ModelSlot
  onSlotChange: (slot: ModelSlot) => void
  autoFocus?: boolean
  /** Conversation id whose unsent draft is kept in local storage. */
  draftId?: string
  /** Bumped when the box should take the caret back: after a Question card was answered, the
   *  focus is on a button that has just disabled itself and the next thing to do is type. */
  focusToken?: number
}) {
  const busy = status === 'submitted' || status === 'streaming'
  const [rejected, setRejected] = useState<string>()
  const box = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    if (focusToken > 0) box.current?.focus()
  }, [focusToken])
  // Stable, so the chips do not re-run their effect on every render of the composer.
  const clearRejected = useCallback(() => setRejected(undefined), [])

  // Not awaited: the composer clears as soon as the message is on its way, not when the turn ends.
  const handleSubmit = (message: PromptInputMessage) => {
    const text = message.text.trim()
    // A file dropped in and sent without a word is a message: the server gives that turn its
    // one sentence, so an empty box with an attachment still sends.
    if ((!text && message.files.length === 0) || busy) return
    setRejected(undefined)
    void onSubmit(text, message.files)
  }

  const input = (
    <PromptInput
      accept={ACCEPT}
      className="rounded-2xl shadow-xs"
      maxFileSize={MAX_FILE_BYTES}
      maxFiles={MAX_FILES}
      multiple
      onError={(error) => setRejected(REJECTED[error.code] ?? error.message)}
      onSubmit={handleSubmit}
    >
      <PromptInputBody>
        <Attachments onClear={clearRejected} rejected={rejected} />
        <PromptInputTextarea
          autoFocus={autoFocus}
          className="min-h-14 text-base md:text-sm"
          placeholder="Ask about your spending, or drop a statement..."
          ref={box}
        />
      </PromptInputBody>
      <PromptInputFooter>
        <PromptInputTools>
          <AttachButton />
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

function AttachButton() {
  const attachments = usePromptInputAttachments()
  return (
    <PromptInputButton
      aria-label="Attach a CSV, PDF or photo"
      onClick={() => attachments.openFileDialog()}
      tooltip="Attach a CSV, a statement PDF or a photo"
      type="button"
      variant="ghost"
    >
      <PaperclipIcon className="size-4" />
    </PromptInputButton>
  )
}

/** The chips above the textarea: what will be sent with this message, each removable. */
function Attachments({ rejected, onClear }: { rejected?: string; onClear: () => void }) {
  const attachments = usePromptInputAttachments()

  useEffect(() => {
    if (attachments.files.length > 0) onClear()
  }, [attachments.files.length, onClear])

  if (attachments.files.length === 0 && !rejected) return null
  return (
    <div className="flex w-full flex-wrap items-center justify-start gap-2 px-3 pt-3">
      {attachments.files.map((file) => (
        <span
          className="inline-flex max-w-full items-center gap-1.5 rounded-full border bg-muted/40 py-1 pl-2.5 pr-1 text-xs"
          key={file.id}
        >
          {file.mediaType?.startsWith('image/') ? (
            <ImageIcon className="size-3.5 shrink-0 text-muted-foreground" />
          ) : (
            <FileTextIcon className="size-3.5 shrink-0 text-muted-foreground" />
          )}
          <span className="truncate">{file.filename ?? 'attachment'}</span>
          <button
            aria-label={`Remove ${file.filename ?? 'attachment'}`}
            className="rounded-full p-0.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            onClick={() => attachments.remove(file.id)}
            type="button"
          >
            <XIcon className="size-3" />
          </button>
        </span>
      ))}
      {rejected && (
        <span className="text-destructive text-xs" role="alert">
          {rejected}
        </span>
      )}
    </div>
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
