import { useChat } from '@ai-sdk/react'
import { useQueryClient } from '@tanstack/react-query'
import { DefaultChatTransport } from 'ai'
import { CircleStopIcon, SparklesIcon, ZapIcon } from 'lucide-react'
import { Fragment, useEffect, useMemo, useRef, useState } from 'react'
import type { StickToBottomContext } from 'use-stick-to-bottom'

import { Conversation, ConversationContent, ConversationScrollButton } from '@/components/ai-elements/conversation'
import { Message, MessageContent, MessageResponse, MessageToolbar } from '@/components/ai-elements/message'
import { Reasoning, ReasoningContent, ReasoningTrigger } from '@/components/ai-elements/reasoning'
import { Shimmer } from '@/components/ai-elements/shimmer'
import { Suggestion } from '@/components/ai-elements/suggestion'
import { Composer } from '@/components/composer'
import { ContextBadge } from '@/components/context-badge'
import { EmptyState } from '@/components/empty-state'
import { SummaryDivider } from '@/components/summary-divider'
import {
  chatUrl,
  conversationQuery,
  conversationsQuery,
  patchConversation,
  slotLabel,
  stopConversation,
  type ChatMessage,
  type ContextStats,
  type ConversationDetail,
  type ModelSlot,
} from '@/lib/api'
import { takePendingPrompt } from '@/lib/pending'
import { readScrollTop, useWorkspace, writeScrollTop } from '@/lib/workspace'

const SLOT_ICONS: Record<ModelSlot, typeof ZapIcon> = { fast: ZapIcon, quality: SparklesIcon }

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

  const { messages, sendMessage, status, stop, error } = useChat<ChatMessage>({
    id: conversation.id,
    messages: conversation.messages,
    transport,
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
    const text = takePendingPrompt(conversation.id)
    if (text) void sendMessage({ text })
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
        {context && <ContextBadge stats={context} />}
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
                  onPickFollowup={(text) => void sendMessage({ text })}
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
            onSubmit={(text) => sendMessage({ text })}
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

/** The stats of the newest turn that reported any, which is what the header badge shows. */
function latestContext(messages: ChatMessage[]): ContextStats | undefined {
  for (let i = messages.length - 1; i >= 0; i--) {
    for (const part of messages[i].parts) {
      if (part.type === 'data-context') return part.data
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

function thinkingMessage(isStreaming: boolean, duration?: number) {
  if (isStreaming) return <Shimmer duration={1}>Thinking...</Shimmer>
  if (duration === undefined) return <p>Thought for a moment</p>
  return <p>Thought for {duration === 1 ? '1 second' : `${duration} seconds`}</p>
}

function TranscriptMessage({
  message,
  isLast,
  streaming,
  slot,
  onPickFollowup,
}: {
  message: ChatMessage
  isLast: boolean
  streaming: boolean
  slot: ModelSlot
  onPickFollowup: (text: string) => void
}) {
  const interrupted = message.metadata?.interrupted === true
  const live = isLast && streaming
  // The turn's own slot, or the conversation's while the turn is still streaming and has no metadata.
  const turnSlot = message.metadata?.model_slot ?? slot
  const TurnIcon = SLOT_ICONS[turnSlot]
  // Only the newest answer offers follow-ups: older ones have already been followed up on.
  const followups =
    isLast && !live ? message.parts.flatMap((p) => (p.type === 'data-followups' ? p.data.suggestions : [])) : []

  return (
    <Message from={message.role}>
      <MessageContent>
        {message.parts.map((part, index) => {
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
          {interrupted && (
            <span className="inline-flex items-center gap-1.5 rounded-full border border-dashed px-2.5 py-0.5">
              <CircleStopIcon className="size-3" />
              Stopped
            </span>
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
