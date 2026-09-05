import { useChat } from '@ai-sdk/react'
import { useQueryClient } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { DefaultChatTransport, type FileUIPart, type ToolUIPart } from 'ai'
import {
  BrainIcon,
  CircleStopIcon,
  FileTextIcon,
  GitCompareIcon,
  ImageIcon,
  SparklesIcon,
  ZapIcon,
} from 'lucide-react'
import { Fragment, useEffect, useMemo, useRef, useState } from 'react'
import type { StickToBottomContext } from 'use-stick-to-bottom'

import { Conversation, ConversationContent, ConversationScrollButton } from '@/components/ai-elements/conversation'
import { Message, MessageContent, MessageResponse, MessageToolbar } from '@/components/ai-elements/message'
import { Reasoning, ReasoningContent, ReasoningTrigger } from '@/components/ai-elements/reasoning'
import { Shimmer } from '@/components/ai-elements/shimmer'
import { Suggestion } from '@/components/ai-elements/suggestion'
import { ChangesetCard } from '@/components/changeset-card'
import { ChartToolStep } from '@/components/chart-tool'
import { Composer } from '@/components/composer'
import { ContextBadge } from '@/components/context-badge'
import { EmptyState } from '@/components/empty-state'
import { AnswerCompare, FeedbackError, Thumbs, useAnswerFeedback } from '@/components/feedback'
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
import { Button } from '@/components/ui/button'
import {
  chatUrl,
  conversationQuery,
  conversationsQuery,
  patchConversation,
  refusalSentence,
  stopConversation,
  type AskUserOutput,
  type AskUserPart,
  type ChatMessage,
  type ContextStats,
  type ConversationDetail,
  type ImportProgress,
  type ModelSlot,
  type PreferenceRating,
} from '@/lib/api'
import { takePendingPrompt } from '@/lib/pending'
import { useSlotLabel } from '@/lib/slots'
import { readScrollTop, useWorkspace, writeScrollTop } from '@/lib/workspace'

const SLOT_ICONS: Record<ModelSlot, typeof ZapIcon> = { fast: ZapIcon, quality: SparklesIcon }

/** The only tools whose turn can be answered a second time: read-only, and they draw no card.
 *
 * An allowlist rather than a list of the tools that write, because that list has to be extended
 * by every ticket that adds a tool and a tool left out of it earns the user a refusal they did
 * not ask for. Must stay in step with `preferences.RERUN_TOOLS`, which is what the server both
 * declares on the rerun and refuses a turn against.
 */
const RERUNNABLE_PARTS = new Set(['tool-query', 'tool-chart'])

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

/** Every rating this chat collected, keyed by the turn and the chart inside it. */
function ratingsByTarget(conversation: ConversationDetail): Map<string, PreferenceRating> {
  return new Map(conversation.ratings.map((rating) => [`${rating.turn_id}:${rating.target ?? ''}`, rating.rating]))
}

export function ChatView({ conversation }: { conversation: ConversationDetail }) {
  const queryClient = useQueryClient()
  const { profile } = useWorkspace()
  const [slot, setSlot] = useState<ModelSlot>(conversation.model_slot)
  const scrollContext = useRememberedScroll(conversation.id)

  const transport = useMemo(
    () =>
      new DefaultChatTransport<ChatMessage>({
        api: chatUrl(conversation.id),
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

  const { messages, sendMessage, setMessages, status, stop, error } = useChat<ChatMessage>({
    id: conversation.id,
    messages: conversation.messages,
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
    void sendMessage(message)
    scrollContext.current?.scrollToBottom()
  }

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

  const changeSlot = async (next: ModelSlot) => {
    setSlot(next)
    await patchConversation(conversation.id, { model_slot: next })
    void queryClient.invalidateQueries(conversationQuery(conversation.id))
  }

  const handleStop = async () => {
    // The server persists the partial turn before it answers; then the fetch is released.
    await stopConversation(conversation.id).catch(() => undefined)
    await stop()
  }

  const streaming = status === 'streaming' || status === 'submitted'
  const ratings = useMemo(() => ratingsByTarget(conversation), [conversation])
  const lastMessage = messages.at(-1)
  const context = latestContext(messages)
  // The turns before this index are the ones the rolling summary stands in for.
  const boundary = conversation.summarized_messages

  // min-h-0 rather than h-full: with the tabs bar above it, a full-height child pushes the page
  // past the viewport and the tabs and this header scroll out of view.
  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col">
      <PageBar title={conversation.title}>
        <span className="ml-auto">
          {context ? (
            <ContextBadge stats={context} />
          ) : (
            <span className="text-muted-foreground text-xs" title="No context reading for this conversation yet">
              &ndash;
            </span>
          )}
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
                  ratings={ratings}
                  slot={slot}
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
            onSlotChange={changeSlot}
            onStop={handleStop}
            onSubmit={(text, files) => send(text ? { text, files } : { files })}
            slot={slot}
            status={status}
          />
          <p className="pt-2 text-center text-2xs text-muted-foreground">
            Numbers come from executed queries, never from the model.
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

/** Every tab comes back where it was left. */
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
      // would overwrite the position this tab was left at.
      if (element.isConnected) writeScrollTop(conversationId, element.scrollTop)
      element.removeEventListener('scroll', remember)
    }
  }, [conversationId])

  return context
}

/** A file the user sent with this message. It links to the stored copy the server kept. */
function AttachmentChip({ part }: { part: FileUIPart }) {
  const Icon = part.mediaType?.startsWith('image/') ? ImageIcon : FileTextIcon
  return (
    <a
      className="not-prose mb-0 inline-flex max-w-full items-center gap-1.5 rounded-full border bg-background/60 px-2.5 py-1 text-xs transition-colors hover:bg-muted"
      href={part.url}
      rel="noreferrer"
      target="_blank"
    >
      <Icon className="size-3.5 shrink-0 text-muted-foreground" />
      <span className="truncate">{part.filename ?? 'attachment'}</span>
    </a>
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
 * The turn is not finished with the user: offering follow-ups and a rating next to it would
 * invite them away from the one thing it is waiting for.
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
  slot,
  ratings,
  onPickFollowup,
  onAnswer,
  progress,
}: {
  message: ChatMessage
  isLast: boolean
  streaming: boolean
  slot: ModelSlot
  ratings: Map<string, PreferenceRating>
  onPickFollowup: (text: string) => void
  onAnswer: (toolCallId: string, output: AskUserOutput) => void
  progress: Record<string, ImportProgress[]>
}) {
  const interrupted = message.metadata?.interrupted === true
  const live = isLast && streaming
  // The turn behind this message, which is what a rating names. It arrives with the metadata at
  // the end of the stream, so the thumbs appear when the answer is stored and not before.
  const turnId = message.metadata?.turn_id
  const feedback = useAnswerFeedback(turnId, ratings.get(`${turnId}:`))
  // A turn that used a tool the rerun does not have is not rerun: no A/B is offered for it.
  const rerunnable = !message.parts.some(
    (part) => part.type.startsWith('tool-') && !RERUNNABLE_PARTS.has(part.type),
  )
  const answerText = message.parts
    .filter((part) => part.type === 'text')
    .map((part) => part.text)
    .join('\n\n')
  // How many durable facts of the profile this turn was given (memory page: /memory).
  const memoriesUsed = message.parts.flatMap((p) => (p.type === 'data-context' ? [p.data.memories] : []))[0] ?? 0
  // The turn's own slot, or the conversation's while the turn is still streaming and has no metadata.
  const turnSlot = message.metadata?.model_slot ?? slot
  const TurnIcon = SLOT_ICONS[turnSlot]
  const slotLabel = useSlotLabel()
  // A turn that is still waiting on a Question card is not over, whatever the stream says.
  const pendingCard = waitingForAnswer(message.parts)
  // Only the newest answer offers follow-ups, and only the newest set of them: a turn that
  // resumed a Question card is one message with one part per round.
  const suggestions = message.parts.filter((p) => p.type === 'data-followups')
  const followups = isLast && !live && !pendingCard ? (suggestions.at(-1)?.data.suggestions ?? []) : []
  const parts = foldReasoning(message.parts)

  return (
    <Message from={message.role}>
      <MessageContent>
        {interrupted && parts.length === 0 && <InterruptedTurn />}
        {parts.map((part, index) => {
          // Judged before any card reads the part: a stopped tool has no result to render.
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
            return <AttachmentChip key={`${message.id}-${index}`} part={part} />
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
                part={part}
                rating={ratings.get(`${turnId}:${part.toolCallId}`)}
                turnId={turnId}
              />
            )
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
            {slotLabel(turnSlot)} model
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
          <span className="ml-auto flex items-center gap-1">
            <FeedbackError message={feedback.problem} />
            {feedback.rating === 'pick' && !feedback.second && <span>Pair collected</span>}
            {feedback.rating === 'down' && rerunnable && !feedback.second && (
              <Button
                className="text-muted-foreground"
                disabled={feedback.asking || !feedback.ready}
                onClick={() => void feedback.compare()}
                size="xs"
                variant="ghost"
              >
                <GitCompareIcon data-icon="inline-start" />
                {feedback.asking ? 'Answering again...' : 'Compare a second answer'}
              </Button>
            )}
            <Thumbs
              busy={feedback.busy}
              disabled={!feedback.ready}
              onRate={(next) => void feedback.rate(next)}
              rating={feedback.rating}
              subject="response"
            />
          </span>
        </MessageToolbar>
      )}

      {feedback.second && (
        <AnswerCompare
          busy={feedback.busy}
          onPick={(which) => void feedback.pick(which)}
          original={answerText}
          picked={feedback.picked}
          second={feedback.second}
        />
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
