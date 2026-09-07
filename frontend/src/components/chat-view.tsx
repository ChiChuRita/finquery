import { useChat } from '@ai-sdk/react'
import { useQueryClient } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { DefaultChatTransport, type FileUIPart, type ToolUIPart } from 'ai'
import {
  AlertTriangleIcon,
  BrainIcon,
  CircleStopIcon,
  CloudIcon,
  HardDriveIcon,
} from 'lucide-react'
import { Fragment, useEffect, useMemo, useRef, useState } from 'react'
import type { StickToBottomContext } from 'use-stick-to-bottom'

import {
  Attachment,
  AttachmentInfo,
  AttachmentPreview,
  Attachments,
} from '@/components/ai-elements/attachments'
import {
  Conversation,
  ConversationContent,
  ConversationDownload,
  ConversationScrollButton,
} from '@/components/ai-elements/conversation'
import { Message, MessageContent, MessageResponse, MessageToolbar } from '@/components/ai-elements/message'
import { Reasoning, ReasoningContent, ReasoningTrigger } from '@/components/ai-elements/reasoning'
import { Shimmer } from '@/components/ai-elements/shimmer'
import { Suggestion } from '@/components/ai-elements/suggestion'
import { ChangesetCard } from '@/components/changeset-card'
import { ChartToolStep } from '@/components/chart-tool'
import { DashboardChartToolStep, DashboardLineToolStep } from '@/components/dashboard-chart-tool'
import { Composer } from '@/components/composer'
import { ContextBadge } from '@/components/context-badge'
import { EmptyState } from '@/components/empty-state'
import { AddedToolStep, DuplicatesToolStep, ImportToolStep, PreviewToolStep } from '@/components/import-tool'
import { LookupToolStep } from '@/components/lookup-tool'
import { MemoryToolStep } from '@/components/memory-tool'
import { PageBar } from '@/components/page'
import { QueryToolStep } from '@/components/query-tool'
import { QuestionCard } from '@/components/question-card'
import { ReviewToolStep, RuleToolStep } from '@/components/rule-tool'
import { SummaryDivider } from '@/components/summary-divider'
import { Step } from '@/components/tool-step'
import { Badge } from '@/components/ui/badge'
import {
  chatUrl,
  conversationQuery,
  conversationsQuery,
  patchConversation,
  refusalSentence,
  stopConversation,
  streamUrl,
  type AskUserOutput,
  type AskUserPart,
  type ChatMessage,
  type ContextStats,
  type ConversationDetail,
  type ImportProgress,
  type ModelKey,
} from '@/lib/api'
import { hasPendingPrompt, takePendingPrompt } from '@/lib/pending'
import { useCatalog, useModelLabel } from '@/lib/catalog'
import { messageToMarkdown, transcriptFilename } from '@/lib/transcript-markdown'
import { readScrollTop, useWorkspace, writeScrollTop } from '@/lib/workspace'

/** Where a turn ran, which is what its chip says next to the model's name. */
const PROVIDER_ICONS = { local: HardDriveIcon, openrouter: CloudIcon }

/** Whether this message is the one a Question card sits on. */
const holdsCall = (message: ChatMessage, toolCallId: string) =>
  message.parts.some((part) => part.type === 'tool-ask_user' && part.toolCallId === toolCallId)

/** The same card with the user's answer on it, or null when it was not open to answer.
 *
 * Built rather than spread: only these two states carry a whole card to answer, and saying so
 * is what makes `input` the card it is instead of the half of one a streaming call may have.
 */
function withAnswer(part: AskUserPart, output: AskUserOutput): AskUserPart | null {
  if (part.state !== 'input-available' && part.state !== 'approval-requested') return null
  return {
    type: 'tool-ask_user',
    toolCallId: part.toolCallId,
    state: 'output-available',
    input: part.input,
    output,
  }
}

export function ChatView({ conversation }: { conversation: ConversationDetail }) {
  const queryClient = useQueryClient()
  const { profile, conversations } = useWorkspace()
  const [modelKey, setModelKey] = useState<ModelKey>(conversation.model_key)
  const scrollContext = useRememberedScroll(conversation.id)
  // The list is polled while anything runs, so it knows before this transcript does that the
  // turn has started or ended. Until it has been loaded, what the conversation itself said.
  const listed = conversations.find((c) => c.id === conversation.id) ?? conversation

  const transport = useMemo(
    () =>
      new DefaultChatTransport<ChatMessage>({
        api: chatUrl(conversation.id),
        // Where the SDK's resume reattaches. Its default is `<api>/<chatId>/stream`, which here
        // would be the chat endpoint with the conversation id twice.
        prepareReconnectToStreamRequest: () => ({ api: streamUrl(conversation.id) }),
        // The server owns the history, so one message travels: the newest, or the one carrying
        // the Question card that was just answered. A card the user comes back to after asking
        // something else is not the newest message, and its answer is what this request is
        // about (ticket 29), so `answered` names the call and this picks the message it is on.
        prepareSendMessagesRequest: ({ id, messages, trigger, messageId, body }) => {
          const answered = (body as { answered?: string } | undefined)?.answered
          const carried = answered ? messages.filter((m) => holdsCall(m, answered)) : messages.slice(-1)
          return { body: { id, messages: carried, trigger, messageId } }
        },
      }),
    [conversation.id],
  )

  // Progress of a running tool, by tool call. Transient parts never reach `messages`, which is
  // the point: the transcript keeps the tool's result, not the counting that led to it.
  const [progress, setProgress] = useState<Record<string, ImportProgress[]>>({})
  // Bumped to send the caret back to the composer, which is what a Question card answer does.
  const [focusToken, setFocusToken] = useState(0)

  // Set when the card just answered was not the newest message. The stream appends the resumed
  // half to the newest assistant message, but the server wrote it into the card's own turn, so
  // the transcript is taken back from the server once the turn ends and the two agree again.
  const resync = useRef(false)

  // Whether the turn that is running is this view's own. The request that started it is already
  // streaming it, and asking to resume on top of that would run the same stream into the
  // transcript twice. It starts true for a conversation opened with a prompt waiting to be
  // sent, which is the one turn this view starts without anybody pressing anything.
  const [sentHere, setSentHere] = useState(() => hasPendingPrompt(conversation.id))
  // Reattach to a turn somebody else started: the tab was closed and opened again, the user
  // switched conversation and came back, or the page was reloaded mid-answer.
  const reattach = listed.running && !sentHere

  const { messages, sendMessage, setMessages, status, stop, error } = useChat<ChatMessage>({
    id: conversation.id,
    messages: conversation.messages,
    resume: reattach,
    transport,
    // No `sendAutomaticallyWhen`: it only ever fires for the newest assistant message, and
    // `addToolOutput` only ever writes to that message too, so a card the user came back to
    // after asking something else swallowed its own answer (ticket 29). `answerCard` below
    // does both jobs for every card, wherever it sits.
    onData: (part) => {
      if (part.type !== 'data-import_progress') return
      const line = part.data
      const key = line.tool_call_id ?? 'running'
      setProgress((previous) => ({
        ...previous,
        [key]: [...(previous[key] ?? []).filter((seen) => seen.stage !== line.stage), line],
      }))
    },
    onFinish: () => {
      // This view is done with that turn, so a turn started elsewhere afterwards is one to
      // reattach to like any other.
      setSentHere(false)
      void queryClient.invalidateQueries(conversationsQuery(profile?.id))
      void queryClient.invalidateQueries(conversationQuery(conversation.id))
      if (!resync.current) return
      resync.current = false
      void queryClient
        .fetchQuery(conversationQuery(conversation.id))
        .then((fresh) => setMessages(fresh.messages))
        .catch(() => undefined)
    },
  })

  // A prompt typed on the empty page is sent once the conversation exists.
  const sentPending = useRef(false)
  useEffect(() => {
    if (sentPending.current) return
    sentPending.current = true
    const pending = takePendingPrompt(conversation.id)
    if (pending?.text) void sendMessage({ text: pending.text, files: pending.files })
    else if (pending?.files?.length) void sendMessage({ files: pending.files })
  }, [conversation.id, sendMessage])

  // Everything the user sends goes through here, so the transcript is always at the bottom when
  // the answer starts. Reading back through a long chat and then asking something otherwise
  // leaves the new turn off screen with nothing moving.
  const send = (message: Parameters<typeof sendMessage>[0]) => {
    setSentHere(true)
    void sendMessage(message)
    scrollContext.current?.scrollToBottom()
  }

  // The tab and the sidebar row draw their spinner from the conversation list, so it is asked
  // again as soon as the server really has this turn (the first chunk is the proof it does).
  useEffect(() => {
    if (status === 'streaming') void queryClient.invalidateQueries(conversationsQuery(profile?.id))
  }, [profile?.id, queryClient, status])

  /** Answer one Question card: put the output on the message the card is on, then send it.
   *
   * The SDK's own pair does neither for an older card. `addToolOutput` writes to the newest
   * message whatever call it was given, and `sendAutomaticallyWhen` only ever looks at the
   * newest message, so answering a card the user came back to did nothing at all: no request,
   * no rules, and the answer lost on the next reload (ticket 29).
   */
  const answerCard = (toolCallId: string, output: AskUserOutput) => {
    const target = messages.find((message) => holdsCall(message, toolCallId))
    if (!target) return
    setSentHere(true)
    // The stream will append the resumed half to the newest message, which is not this one.
    resync.current = target !== messages.at(-1)
    setMessages(
      messages.map((message) =>
        message === target
          ? {
              ...message,
              parts: message.parts.map((part) =>
                part.type === 'tool-ask_user' && part.toolCallId === toolCallId
                  ? (withAnswer(part, output) ?? part)
                  : part,
              ),
            }
          : message,
      ),
    )
    void sendMessage(undefined, { body: { answered: toolCallId } })
    scrollContext.current?.scrollToBottom()
    // The button that was clicked has just disabled itself, so the caret is nowhere. The next
    // thing to do after answering a card is to type.
    setFocusToken((token) => token + 1)
  }

  const changeModel = async (next: ModelKey) => {
    // The running turn keeps the entry it started on; this decides the next one.
    setModelKey(next)
    await patchConversation(conversation.id, { model_key: next })
    void queryClient.invalidateQueries(conversationQuery(conversation.id))
  }

  const handleStop = async () => {
    // The server persists the partial turn before it answers; then the fetch is released.
    await stopConversation(conversation.id).catch(() => undefined)
    await stop()
  }

  const streaming = status === 'streaming' || status === 'submitted'
  // A turn is being answered for this conversation: here, in another tab, or with nobody
  // watching it at all. The composer is closed for all three, and Stop ends any of them.
  const running = streaming || listed.running
  const lastMessage = messages.at(-1)
  const context = latestContext(messages)
  // The turns before this index are the ones the rolling summary stands in for.
  const boundary = conversation.summarized_messages

  // min-h-0 rather than h-full: a full-height child of the scroll container pushes the page past
  // the viewport and takes this header out of view with it.
  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col">
      <PageBar title={conversation.title}>
        <span className="ml-auto flex items-center gap-2">
          {context ? (
            <ContextBadge stats={context} />
          ) : (
            <span className="text-muted-foreground text-xs" title="No context reading for this conversation yet">
              &ndash;
            </span>
          )}
          {/* The whole audit trail, in a file: every step, card and figure as markdown. */}
          <ConversationDownload
            aria-label="Download this conversation"
            className="static size-7 text-muted-foreground"
            disabled={messages.length === 0}
            filename={transcriptFilename(conversation.title)}
            formatMessage={messageToMarkdown}
            messages={messages}
            size="icon-sm"
            title="Download this conversation as markdown"
            variant="ghost"
          />
        </span>
      </PageBar>

      <Conversation className="flex-1" contextRef={scrollContext} initial={false}>
        <ConversationContent className="mx-auto w-full max-w-3xl gap-6 px-6 py-8">
          {messages.length === 0 && !streaming ? (
            <EmptyState onPick={(text) => send({ text })} />
          ) : (
            messages.map((message, index) => (
              <Fragment key={message.id}>
                {boundary > 0 && index === boundary && conversation.summary && (
                  <SummaryDivider
                    conversationId={conversation.id}
                    summary={conversation.summary}
                    turns={conversation.summarized_turns}
                  />
                )}
                <TranscriptMessage
                  isLast={message === lastMessage}
                  message={message}
                  onAnswer={answerCard}
                  onPickFollowup={(text) => send({ text })}
                  progress={progress}
                  modelKey={modelKey}
                  streaming={streaming}
                />
              </Fragment>
            ))
          )}
          {status === 'submitted' && (
            <Message from="assistant">
              <Shimmer className="text-sm" duration={1.5}>
                Thinking...
              </Shimmer>
            </Message>
          )}
          {error && (
            <div className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-destructive text-sm" role="alert">
              {refusalSentence(error)}
            </div>
          )}
        </ConversationContent>
        <ConversationScrollButton aria-label="Jump to the newest message" title="Jump to the newest message" />
      </Conversation>

      <div className="shrink-0 px-6 pb-5">
        <div className="mx-auto w-full max-w-3xl">
          <Composer
            draftId={conversation.id}
            focusToken={focusToken}
            modelKey={modelKey}
            onModelChange={changeModel}
            onStop={handleStop}
            onSubmit={(text, files) => send(text ? { text, files } : { files })}
            // Running is running, whoever is watching: the box is closed and the button stops
            // the turn, in the tab that started it and in one that only came to look.
            status={running && status === 'ready' ? 'streaming' : status}
          />
          <p className="pt-2 text-center text-2xs text-muted-foreground">
            {running
              ? 'This chat is answering. It keeps going if you switch chats or close the tab.'
              : 'Numbers come from executed queries, never from the model.'}
          </p>
        </div>
      </div>
    </div>
  )
}

/** The stats of the newest turn that reported any, which is what the header badge shows.
 *
 * A conversation from before the part carried token counts, and a turn nobody streamed (the
 * seeded review conversation), have no usable reading. The header shows a dash for those
 * rather than a percentage computed from undefined.
 */
function latestContext(messages: ChatMessage[]): ContextStats | undefined {
  for (let i = messages.length - 1; i >= 0; i--) {
    for (const part of messages[i].parts) {
      if (part.type !== 'data-context') continue
      const stats = part.data
      if (Number.isFinite(stats?.used) && Number.isFinite(stats?.budget) && stats.budget > 0) return stats
    }
  }
  return undefined
}

const SETTLE_MS = 300

/** Every chat comes back where it was left. */
function useRememberedScroll(conversationId: string) {
  const context = useRef<StickToBottomContext>(null)

  useEffect(() => {
    const element = context.current?.scrollRef.current
    if (!element) return
    const saved = readScrollTop(conversationId)
    const restore = () => {
      element.scrollTop = saved ?? element.scrollHeight
    }

    let timer: number | undefined
    const remember = () => {
      window.clearTimeout(timer)
      timer = window.setTimeout(() => writeScrollTop(conversationId, element.scrollTop), 200)
    }

    // Markdown, fonts and the reasoning panels settle over the first frames, and until they do
    // the transcript is too short to hold the saved position. So it is set again once the height
    // is final, and only then does scrolling start being recorded.
    restore()
    const frame = requestAnimationFrame(restore)
    const settled = window.setTimeout(() => {
      restore()
      element.addEventListener('scroll', remember, { passive: true })
    }, SETTLE_MS)

    return () => {
      cancelAnimationFrame(frame)
      window.clearTimeout(settled)
      window.clearTimeout(timer)
      // React has already detached the node here, and a detached node reports scrollTop 0, which
      // would overwrite the position this chat was left at.
      if (element.isConnected) writeScrollTop(conversationId, element.scrollTop)
      element.removeEventListener('scroll', remember)
    }
  }, [conversationId])

  return context
}

const isPhoto = (part: FileUIPart) => part.mediaType?.startsWith('image/') === true

/** The files the user sent with this message, each one a link to the copy the server stored.
 *
 * A photo is shown as a photo: the receipt dropped on the composer is what the user has to
 * recognize the message by, and a grey icon with a file name is not it. A CSV and a statement
 * PDF have nothing to look at, so those stay chips.
 */
function MessageAttachments({ files, messageId }: { files: FileUIPart[]; messageId: string }) {
  const photos = files.filter(isPhoto)
  const documents = files.filter((file) => !isPhoto(file))
  // Ids come from the position in the message, not in the row being drawn: the two rows are
  // slices of the same list and would otherwise both start at zero.
  const link = (file: FileUIPart) => {
    const id = `${messageId}-file-${files.indexOf(file)}`
    return (
      <a href={file.url} key={id} rel="noreferrer" target="_blank" title={file.filename}>
        {/* `AttachmentInfo` draws nothing in the grid variant, so one link serves both rows. */}
        <Attachment data={{ ...file, id }}>
          <AttachmentPreview />
          <AttachmentInfo className="max-w-48 text-xs" />
        </Attachment>
      </a>
    )
  }
  return (
    <div className="not-prose mb-0 flex w-full flex-col gap-2">
      {photos.length > 0 && (
        // The library's grid pushes itself to the right edge; inside this bubble it reads
        // left to right like everything else in it.
        <Attachments className="ml-0" variant="grid">
          {photos.map(link)}
        </Attachments>
      )}
      {documents.length > 0 && <Attachments variant="inline">{documents.map(link)}</Attachments>}
    </div>
  )
}

function thinkingMessage(isStreaming: boolean, duration?: number) {
  if (isStreaming) return <Shimmer duration={1}>Thinking...</Shimmer>
  if (duration === undefined) return <p>Thought for a moment</p>
  return <p>Thought for {duration === 1 ? '1 second' : `${duration} seconds`}</p>
}

type MessagePart = ChatMessage['parts'][number]

/** The part types below draw something. `step-start`, the data parts and a tool without a card
 *  take up no room, so they must not separate two panels either. */
/** The parts this component renders nothing for.
 *
 * Listed the silent way round on purpose. An allowlist of what draws has to be extended by
 * every ticket that adds a tool, and a tool left out of it does not just break the fold below,
 * it disappears from the transcript. Here the cost of forgetting a silent part is two thinking
 * panels where one belongs, and a new tool is visible by default.
 *
 * The badge reads `data-context`, the follow-ups are drawn under the message, and
 * `data-import_progress` is transient and shown inside the import step.
 */
const SILENT = new Set<string>(['data-context', 'data-followups', 'data-import_progress', 'step-start'])

const drawn = (part: MessagePart) =>
  !SILENT.has(part.type) && (part.type !== 'text' || part.text.trim() !== '')

type ReasoningPart = MessagePart & { type: 'reasoning' }

const isReasoning = (part: MessagePart): part is ReasoningPart => part.type === 'reasoning'

/** One turn thinks once, in one panel, above the steps it led to.
 *
 * A tool call ends a model response, so a turn with two tools produces three reasoning parts
 * with a step between each pair. Rendered as they arrive that is three panels, each labelled
 * with the turn's whole thinking time, which reads as three times the thinking that happened.
 * They are all folded into one instead: one panel, one honest duration.
 *
 * The panel goes to the top of the turn rather than where its first block happened to land. A
 * model that calls a tool without thinking first, and a sub-agent's narration (which the server
 * puts back after the step it belongs to), both leave the turn's only reasoning part *below*
 * the card, and three of eight chart turns drew their thinking under the chart (e2e of
 * 2026-09-05, m7). One position, whichever way the turn ran.
 */
function foldReasoning(parts: MessagePart[]): MessagePart[] {
  const visible = parts.filter(drawn)
  const thinking = visible.filter(isReasoning)
  const rest = visible.filter((part) => !isReasoning(part))
  if (thinking.length === 0) return rest
  const folded: ReasoningPart = {
    ...thinking[0],
    // The panel is still streaming while its newest block is.
    state: thinking[thinking.length - 1].state,
    text: thinking.map((part) => part.text).join('\n\n'),
  }
  return [folded, ...rest]
}

// The states a tool call arrives in before it has a result: streaming its arguments, waiting to
// run, or dumped as pending after a reload.
const OPEN_TOOL = new Set(['input-streaming', 'input-available', 'approval-requested'])

/** A tool step of a turn that Stop cut short, told apart from one that really returned.
 *
 * A cancelled run closes the call it was in the middle of with a plain sentence where the
 * tool's own result object belongs, and a call whose arguments were still streaming stays open
 * for good. Either way the card below would read fields off something that has none:
 * `output.notes.length` on a chart, `changeset.rows.length` on a proposal. That read is what
 * replaced the whole page with the error boundary when Stop landed in the middle of a chart
 * (e2e of 2026-09-05, B1), and it is guarded here, once, before any card sees the part.
 *
 * A Question card is the exception among open calls: a stopped turn's card is still answerable,
 * and answering it resumes the run.
 */
function stoppedTool(part: MessagePart, interrupted: boolean): boolean {
  if (!part.type.startsWith('tool-')) return false
  const tool = part as ToolUIPart
  if (tool.state === 'output-available') {
    // Every tool of this agent answers with an object except `remember`, whose whole result is
    // one sentence, so anything else here is not a result at all. `remember` writes a row and
    // returns; there is no window to stop it in, and an open call is still caught below.
    if (part.type === 'tool-remember') return false
    return typeof tool.output !== 'object' || tool.output === null
  }
  if (!interrupted || part.type === 'tool-ask_user') return false
  return OPEN_TOOL.has(tool.state)
}

/** The sentence a tool that failed unexpectedly left behind, or nothing.
 *
 * The server turns any exception inside a tool into `{tool_failed, error}` (`agent.guarded`),
 * so the transcript shows a step the user can read instead of the turn ending on a raw error.
 * Judged before the per-tool renderers, which all read their own tool's fields.
 */
function failedTool(part: MessagePart): string | undefined {
  if (!part.type.startsWith('tool-')) return undefined
  const tool = part as ToolUIPart
  if (tool.state !== 'output-available' || typeof tool.output !== 'object' || tool.output === null) {
    return undefined
  }
  const output = tool.output as { tool_failed?: boolean; error?: string }
  if (!output.tool_failed) return undefined
  return output.error ?? 'That step could not be finished.'
}

/** The step a failed tool leaves in the transcript: one sentence, never an exception. */
function FailedToolStep({ reason }: { reason: string }) {
  return (
    <Step tone="error">
      <AlertTriangleIcon aria-hidden="true" className="size-3.5 shrink-0" />
      <span>{reason}</span>
    </Step>
  )
}

/** The step a stopped tool leaves in the transcript. The partial turn keeps it (m6). */
function StoppedToolStep({ type }: { type: string }) {
  return (
    <Step>
      <CircleStopIcon aria-hidden="true" className="size-3.5 shrink-0" />
      <span>
        The <span className="font-medium">{type.slice('tool-'.length).replaceAll('_', ' ')}</span> step was
        stopped before it finished, so it has no result.
      </span>
    </Step>
  )
}

/** A turn that was cut off before it wrote anything at all.
 *
 * The server marks a turn interrupted when the run behind it stopped existing: the browser
 * hung up mid-answer, or the process it was running in did. What is left is the question with
 * nothing under it, and without a word here that reads as an answer that is still coming.
 */
function InterruptedTurn() {
  return (
    <Step>
      <CircleStopIcon aria-hidden="true" className="size-3.5 shrink-0" />
      <span>This turn was interrupted before an answer was written. Ask again to continue.</span>
    </Step>
  )
}

// Mirrors `question-card.OPEN`, plus the state a card streaming its rows is in: the states a
// parked `ask_user` call arrives in, live and after a reload.
const OPEN_CALL = new Set(['input-streaming', 'input-available', 'approval-requested'])

/** A Question card of this message that nobody has answered yet.
 *
 * The turn is not finished with the user: offering follow-ups next to it would invite them
 * away from the one thing it is waiting for.
 */
function waitingForAnswer(parts: MessagePart[]): boolean {
  return parts.some((part) => part.type === 'tool-ask_user' && OPEN_CALL.has(part.state))
}

/** How tall a panel of thinking may grow while the turn runs. Past that it scrolls itself, so
 *  the tool step and the answer below it stay on screen. */
const THINKING_CAP = 'max-h-56 overflow-y-auto pr-1 [scrollbar-color:var(--border)_transparent] [scrollbar-width:thin]'

/** The thinking of one turn: open and capped while it streams, folded away once the answer starts.
 *
 * The panel's own state is controlled here rather than left to the component, which closes
 * itself exactly once: a turn that thinks, calls a tool and thinks again reopened it and then
 * stayed open, leaving the model's scratch work above the answer for good. The cap follows the
 * same signal, so a panel that has folded reserves no height.
 */
function ThinkingPanel({
  text,
  isStreaming,
  duration,
}: {
  text: string
  isStreaming: boolean
  duration?: number
}) {
  const box = useRef<HTMLDivElement>(null)
  const [open, setOpen] = useState(isStreaming)
  const streamed = useRef(isStreaming)

  // Opening and folding follow the stream. Between two of those moments the reader's own click
  // stands, so a panel opened to read it does not snap shut under them.
  useEffect(() => {
    if (streamed.current === isStreaming) return
    streamed.current = isStreaming
    setOpen(isStreaming)
  }, [isStreaming])

  useEffect(() => {
    if (!isStreaming) return
    const element = box.current
    if (element) element.scrollTop = element.scrollHeight
  }, [isStreaming, text])

  return (
    <Reasoning
      className="mb-0 w-full"
      duration={duration}
      isStreaming={isStreaming}
      onOpenChange={setOpen}
      open={open}
    >
      <ReasoningTrigger getThinkingMessage={thinkingMessage} />
      <ReasoningContent className={isStreaming ? THINKING_CAP : undefined} ref={box}>
        {text}
      </ReasoningContent>
    </Reasoning>
  )
}

function TranscriptMessage({
  message,
  isLast,
  streaming,
  modelKey,
  onPickFollowup,
  onAnswer,
  progress,
}: {
  message: ChatMessage
  isLast: boolean
  streaming: boolean
  modelKey: ModelKey
  onPickFollowup: (text: string) => void
  onAnswer: (toolCallId: string, output: AskUserOutput) => void
  progress: Record<string, ImportProgress[]>
}) {
  const interrupted = message.metadata?.interrupted === true
  const live = isLast && streaming
  // The turn behind this message, which is what a chart card of it names. It arrives with the
  // metadata at the end of the stream, so a card can add its chart to the dashboard at once.
  const turnId = message.metadata?.turn_id
  // How many durable facts of the profile this turn was given (memory page: /memory).
  const memoriesUsed = message.parts.flatMap((p) => (p.type === 'data-context' ? [p.data.memories] : []))[0] ?? 0
  // The turn's own entry, or the conversation's while the turn is still streaming and has no
  // metadata. A turn never gets relabelled when the chat is switched to another model.
  const turnKey = message.metadata?.model_key ?? modelKey
  const modelLabel = useModelLabel()
  const provider = useCatalog().entry(turnKey)?.provider ?? 'openrouter'
  const TurnIcon = PROVIDER_ICONS[provider]
  // A turn that is still waiting on a Question card is not over, whatever the stream says.
  const pendingCard = waitingForAnswer(message.parts)
  // Only the newest answer offers follow-ups, and only the newest set of them: a turn that
  // resumed a Question card is one message with one part per round.
  const suggestions = message.parts.filter((p) => p.type === 'data-followups')
  const followups = isLast && !live && !pendingCard ? (suggestions.at(-1)?.data.suggestions ?? []) : []
  const parts = foldReasoning(message.parts)
  // What was attached to this message, drawn as one row rather than one chip per part.
  const files = parts.filter((part) => part.type === 'file')

  return (
    <Message from={message.role}>
      <MessageContent>
        {interrupted && parts.length === 0 && <InterruptedTurn />}
        {parts.map((part, index) => {
          // Judged before any card reads the part: neither a failed nor a stopped tool has
          // the result its own renderer would read.
          const failed = failedTool(part)
          if (failed !== undefined) {
            return <FailedToolStep key={`${message.id}-${index}`} reason={failed} />
          }
          if (stoppedTool(part, interrupted)) {
            return <StoppedToolStep key={`${message.id}-${index}`} type={part.type} />
          }
          if (part.type === 'reasoning') {
            const isStreaming = live && part.state === 'streaming'
            // The server measures the duration; while streaming the component counts by itself.
            const seconds = message.metadata?.thinking_seconds
            const duration = !isStreaming && seconds !== undefined ? Math.max(1, Math.round(seconds)) : undefined
            return (
              <ThinkingPanel
                duration={duration}
                isStreaming={isStreaming}
                key={`${message.id}-thinking`}
                text={part.text}
              />
            )
          }
          if (part.type === 'tool-query') {
            return <QueryToolStep key={`${message.id}-${index}`} part={part} />
          }
          if (part.type === 'tool-ask_user') {
            return (
              <QuestionCard
                key={part.toolCallId}
                onAnswer={(output) => onAnswer(part.toolCallId, output)}
                part={part}
              />
            )
          }
          if (part.type === 'tool-import_file') {
            return (
              <ImportToolStep key={part.toolCallId} part={part} progress={progress[part.toolCallId] ?? []} />
            )
          }
          if (part.type === 'tool-extract_transaction') {
            return <PreviewToolStep key={part.toolCallId} part={part} />
          }
          if (part.type === 'tool-add_transaction') {
            return <AddedToolStep key={part.toolCallId} part={part} />
          }
          if (part.type === 'file') {
            // Every file of this message is drawn once, together, where the first of them sits.
            return part === files[0] ? (
              <MessageAttachments files={files} key={`${message.id}-files`} messageId={message.id} />
            ) : null
          }
          if (part.type === 'tool-set_rule') {
            return <RuleToolStep key={`${message.id}-${index}`} part={part} />
          }
          if (part.type === 'tool-review_batch') {
            return <ReviewToolStep key={`${message.id}-${index}`} part={part} />
          }
          if (part.type === 'tool-review_duplicates') {
            return <DuplicatesToolStep key={`${message.id}-${index}`} part={part} />
          }
          if (part.type === 'tool-remember') {
            return <MemoryToolStep key={`${message.id}-${index}`} part={part} />
          }
          if (part.type === 'tool-propose_changeset' || part.type === 'tool-apply_simple_edit') {
            return <ChangesetCard key={`${message.id}-${index}`} part={part} />
          }
          if (part.type === 'tool-chart') {
            return (
              <ChartToolStep
                key={`${message.id}-${index}`}
                // The sub-agent narrates its steps into the turn's thinking; a chart still being
                // made reads them to advance its own rail.
                narration={live ? parts.find(isReasoning)?.text : undefined}
                part={part}
                turnId={turnId}
              />
            )
          }
          if (part.type === 'tool-show_dashboard_chart' || part.type === 'tool-edit_dashboard_chart') {
            return <DashboardChartToolStep key={`${message.id}-${index}`} part={part} />
          }
          if (part.type === 'tool-rename_dashboard_chart' || part.type === 'tool-remove_dashboard_chart') {
            return <DashboardLineToolStep key={`${message.id}-${index}`} part={part} />
          }
          if (part.type === 'tool-lookup_merchant') {
            return <LookupToolStep key={`${message.id}-${index}`} part={part} />
          }
          if (part.type === 'text') {
            return message.role === 'user' ? (
              <p className="whitespace-pre-wrap" key={`${message.id}-${index}`}>
                {part.text}
              </p>
            ) : (
              <MessageResponse isAnimating={live} key={`${message.id}-${index}`}>
                {part.text}
              </MessageResponse>
            )
          }
          return null
        })}
      </MessageContent>

      {message.role === 'assistant' && !live && !pendingCard && (
        <MessageToolbar className="mt-1 justify-start gap-2 text-muted-foreground text-xs">
          <Badge className="font-normal text-muted-foreground" variant="outline">
            <TurnIcon />
            {modelLabel(turnKey)}
          </Badge>
          {memoriesUsed > 0 && (
            <Badge asChild className="font-normal text-muted-foreground" variant="outline">
              <Link title="What the assistant remembers about you" to="/memory">
                <BrainIcon />
                {memoriesUsed === 1 ? '1 memory' : `${memoriesUsed} memories`} used
              </Link>
            </Badge>
          )}
          {interrupted && (
            <Badge className="border-dashed font-normal text-muted-foreground" variant="outline">
              <CircleStopIcon />
              Stopped
            </Badge>
          )}
        </MessageToolbar>
      )}

      {followups.length > 0 && (
        <div className="mt-1 w-full">
          <p className="pb-1.5 text-muted-foreground text-xs">Ask next</p>
          <div className="flex flex-wrap gap-2">
            {followups.map((suggestion) => (
              <Suggestion className="h-7 text-xs" key={suggestion} onClick={onPickFollowup} suggestion={suggestion} />
            ))}
          </div>
        </div>
      )}
    </Message>
  )
}
