import type { ChatStatus, FileUIPart } from 'ai'
import { PaperclipIcon } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'

import {
  Attachment,
  AttachmentHoverCard,
  AttachmentHoverCardContent,
  AttachmentHoverCardTrigger,
  AttachmentInfo,
  AttachmentPreview,
  AttachmentRemove,
  Attachments,
  getAttachmentLabel,
  getMediaCategory,
  type AttachmentData,
} from '@/components/ai-elements/attachments'
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
import type { ModelKey } from '@/lib/api'
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
  modelKey,
  onModelChange,
  autoFocus,
  draftId,
  focusToken = 0,
}: {
  status: ChatStatus
  onSubmit: (text: string, files: FileUIPart[]) => void | Promise<void>
  onStop?: () => void
  modelKey: ModelKey | undefined
  onModelChange: (key: ModelKey) => void
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
        <AttachedFiles onClear={clearRejected} rejected={rejected} />
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
          <ModelPicker onChange={onModelChange} value={modelKey} />
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

/** One chip: a photo by its thumbnail, a CSV or a PDF by its icon, both with the name and an X.
 *
 * A photo gets a hover card with the picture at readable size, which is the one thing the old
 * chip row could not do: a receipt is told from another receipt by looking at it, not by its
 * file name. The remove button stays visible instead of appearing on hover (the library's
 * inline variant hides it): a touch screen has no hover, and taking a file back out is the only
 * thing there is to do to a chip.
 */
function Chip({ file, onRemove }: { file: AttachmentData; onRemove: () => void }) {
  const label = getAttachmentLabel(file)
  const chip = (
    <Attachment data={file} onRemove={onRemove}>
      <AttachmentPreview />
      <AttachmentInfo className="max-w-48 text-xs" />
      <AttachmentRemove className="opacity-100" label={`Remove ${label}`} />
    </Attachment>
  )
  if (getMediaCategory(file) !== 'image' || file.type !== 'file' || !file.url) return chip
  return (
    <AttachmentHoverCard>
      <AttachmentHoverCardTrigger asChild>{chip}</AttachmentHoverCardTrigger>
      <AttachmentHoverCardContent>
        <img alt={label} className="max-h-80 w-72 rounded-md object-contain" src={file.url} />
      </AttachmentHoverCardContent>
    </AttachmentHoverCard>
  )
}

/** The chips above the textarea: what will be sent with this message, each removable.
 *
 * Only the markup is the library's. Every rule about what this box takes (`ACCEPT`, `MAX_FILES`,
 * `MAX_FILE_BYTES`) and every sentence it refuses with (`REJECTED`) stays in `prompt-input`,
 * so a rejected file is still answered in this app's own words.
 */
function AttachedFiles({ rejected, onClear }: { rejected?: string; onClear: () => void }) {
  const attachments = usePromptInputAttachments()

  useEffect(() => {
    if (attachments.files.length > 0) onClear()
  }, [attachments.files.length, onClear])

  if (attachments.files.length === 0 && !rejected) return null
  return (
    <div className="flex w-full flex-wrap items-center justify-start gap-2 px-3 pt-3">
      <Attachments variant="inline">
        {attachments.files.map((file) => (
          <Chip file={file} key={file.id} onRemove={() => attachments.remove(file.id)} />
        ))}
      </Attachments>
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
