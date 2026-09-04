import { useChat } from '@ai-sdk/react'
import { useQueryClient } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { DefaultChatTransport, lastAssistantMessageIsCompleteWithToolCalls, type FileUIPart } from 'ai'
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
import { AddedToolStep, ImportToolStep, PreviewToolStep } from '@/components/import-tool'
import { LookupToolStep } from '@/components/lookup-tool'
import { MemoryToolStep } from '@/components/memory-tool'
import { QueryToolStep } from '@/components/query-tool'
import { QuestionCard } from '@/components/question-card'
import { ReviewToolStep, RuleToolStep } from '@/components/rule-tool'
import { SummaryDivider } from '@/components/summary-divider'
import { Button } from '@/components/ui/button'
import {
  chatUrl,
  conversationQuery,
  conversationsQuery,
  patchConversation,
  slotLabel,
  stopConversation,
  type AskUserOutput,
  type ChatMessage,
  type ContextStats,
  type ConversationDetail,
  type ImportProgress,
  type ModelSlot,
  type PreferenceRating,
} from '@/lib/api'
import { takePendingPrompt } from '@/lib/pending'
import { readScrollTop, useWorkspace, writeScrollTop } from '@/lib/workspace'

const SLOT_ICONS: Record<ModelSlot, typeof ZapIcon> = { fast: ZapIcon, quality: SparklesIcon }

/** Tools whose turn cannot be answered a second time: they wrote, or they asked a human.
 *
 * The server refuses the rerun for exactly these, and the UI does not offer it either, so a
 * changeset is never proposed twice and a Question card never parks a second run.
 */
// Must stay in step with `preferences.MUTATING_TOOLS`: the server refuses an A/B for a turn
// that used one of these, so offering the button here would only earn a 409.
const WRITING_PARTS = new Set([
  'tool-propose_changeset',
  'tool-apply_simple_edit',
  'tool-set_rule',
  'tool-ask_user',
  'tool-import_file',
  'tool-add_transaction',
])

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
        // The server owns the history, so only the newest message travels.
        prepareSendMessagesRequest: ({ id, messages, trigger, messageId }) => ({
          body: { id, messages: messages.slice(-1), trigger, messageId },
        }),
      }),
    [conversation.id],
  )

  // Progress of a running tool, by tool call. Transient parts never reach `messages`, which is
  // the point: the transcript keeps the tool's result, not the counting that led to it.
  const [progress, setProgress] = useState<Record<string, ImportProgress[]>>({})

  const { messages, sendMessage, status, stop, error, addToolOutput } = useChat<ChatMessage>({
    id: conversation.id,
    messages: conversation.messages,
    transport,
    // A Question card answers a tool call the server left open. Once the output is in, the next
    // request goes out by itself and the run picks up where it parked.
    sendAutomaticallyWhen: lastAssistantMessageIsCompleteWithToolCalls,
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
      <div className="flex h-11 shrink-0 items-center gap-3 border-b px-6">
        <p className="min-w-0 flex-1 truncate font-medium text-sm" title={conversation.title}>
          {conversation.title}
        </p>
        {context ? (
          <ContextBadge stats={context} />
        ) : (
          <span className="text-muted-foreground text-xs" title="No context reading for this conversation yet">
            &ndash;
          </span>
        )}
      </div>

      <Conversation className="flex-1" contextRef={scrollContext} initial={false}>
        <ConversationContent className="mx-auto w-full max-w-3xl gap-6 px-6 py-8">
          {messages.length === 0 && !streaming ? (
            <EmptyState onPick={(text) => void sendMessage({ text })} />
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
                  onAnswer={(toolCallId, output) => void addToolOutput({ tool: 'ask_user', toolCallId, output })}
                  onPickFollowup={(text) => void sendMessage({ text })}
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
              {error.message}
            </div>
          )}
        </ConversationContent>
        <ConversationScrollButton />
      </Conversation>

      <div className="shrink-0 px-6 pb-5">
        <div className="mx-auto w-full max-w-3xl">
          <Composer
            draftId={conversation.id}
            onSlotChange={changeSlot}
            onStop={handleStop}
            onSubmit={(text, files) => sendMessage(text ? { text, files } : { files })}
            slot={slot}
            status={status}
          />
          <p className="pt-2 text-center text-[11px] text-muted-foreground">
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

/** One turn can think several times in a row (a tool call ends a model response). One panel.
 *
 * `step-start` parts sit between the steps of a turn and render nothing, so they are dropped
 * first: otherwise a sub-agent's narration and the thinking that follows it would show as two
 * panels for one pause.
 */
function foldReasoning(parts: MessagePart[]): MessagePart[] {
  const folded: MessagePart[] = []
  for (const part of parts.filter((candidate) => candidate.type !== 'step-start')) {
    const previous = folded.at(-1)
    if (part.type === 'reasoning' && previous?.type === 'reasoning') {
      folded[folded.length - 1] = { ...previous, state: part.state, text: `${previous.text}\n\n${part.text}` }
      continue
    }
    folded.push(part)
  }
  return folded
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
  // A turn that wrote something is not rerun: the A/B is not offered for it.
  const rerunnable = !message.parts.some((part) => WRITING_PARTS.has(part.type))
  const answerText = message.parts
    .filter((part) => part.type === 'text')
    .map((part) => part.text)
    .join('\n\n')
  // How many durable facts of the profile this turn was given (memory page: /memory).
  const memoriesUsed = message.parts.flatMap((p) => (p.type === 'data-context' ? [p.data.memories] : []))[0] ?? 0
  // The turn's own slot, or the conversation's while the turn is still streaming and has no metadata.
  const turnSlot = message.metadata?.model_slot ?? slot
  const TurnIcon = SLOT_ICONS[turnSlot]
  // Only the newest answer offers follow-ups, and only the newest set of them: a turn that
  // resumed a Question card is one message with one part per round.
  const suggestions = message.parts.filter((p) => p.type === 'data-followups')
  const followups = isLast && !live ? (suggestions.at(-1)?.data.suggestions ?? []) : []

  return (
    <Message from={message.role}>
      <MessageContent>
        {foldReasoning(message.parts).map((part, index) => {
          if (part.type === 'reasoning') {
            const isStreaming = live && part.state === 'streaming'
            // The server measures the duration; while streaming the component counts by itself.
            const seconds = message.metadata?.thinking_seconds
            const duration = !isStreaming && seconds !== undefined ? Math.max(1, Math.round(seconds)) : undefined
            return (
              <Reasoning className="mb-0 w-full" duration={duration} isStreaming={isStreaming} key={`${message.id}-${index}`}>
                <ReasoningTrigger getThinkingMessage={thinkingMessage} />
                <ReasoningContent>{part.text}</ReasoningContent>
              </Reasoning>
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

      {message.role === 'assistant' && !live && (
        <MessageToolbar className="mt-1 justify-start gap-2 text-muted-foreground text-xs">
          <span className="inline-flex items-center gap-1.5 rounded-full border bg-muted/40 px-2.5 py-0.5">
            <TurnIcon className="size-3" />
            {slotLabel(turnSlot)} model
          </span>
          {memoriesUsed > 0 && (
            <Link
              className="inline-flex items-center gap-1.5 rounded-full border bg-muted/40 px-2.5 py-0.5 transition-colors hover:text-foreground"
              title="What the assistant remembers about you"
              to="/memory"
            >
              <BrainIcon className="size-3" />
              {memoriesUsed === 1 ? '1 memory' : `${memoriesUsed} memories`} used
            </Link>
          )}
          {interrupted && (
            <span className="inline-flex items-center gap-1.5 rounded-full border border-dashed px-2.5 py-0.5">
              <CircleStopIcon className="size-3" />
              Stopped
            </span>
          )}
          <span className="ml-auto flex items-center gap-1">
            <FeedbackError message={feedback.problem} />
            {feedback.rating === 'pick' && !feedback.second && <span>Pair collected</span>}
            {feedback.rating === 'down' && rerunnable && !feedback.second && (
              <Button
                className="h-6 gap-1.5 px-2 text-muted-foreground text-xs"
                disabled={feedback.asking || !feedback.ready}
                onClick={() => void feedback.compare()}
                size="sm"
                variant="ghost"
              >
                <GitCompareIcon className="size-3" />
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
