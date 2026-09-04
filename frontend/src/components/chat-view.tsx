import { useChat } from '@ai-sdk/react'
import { useQueryClient } from '@tanstack/react-query'
import { DefaultChatTransport } from 'ai'
import { CircleStopIcon } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'

import { Conversation, ConversationContent, ConversationScrollButton } from '@/components/ai-elements/conversation'
import { Message, MessageContent, MessageResponse } from '@/components/ai-elements/message'
import { Reasoning, ReasoningContent, ReasoningTrigger } from '@/components/ai-elements/reasoning'
import { Shimmer } from '@/components/ai-elements/shimmer'
import { Composer } from '@/components/composer'
import { EmptyState } from '@/components/empty-state'
import { QueryToolStep } from '@/components/query-tool'
import { MODEL_SLOTS } from '@/lib/api'
import {
  chatUrl,
  conversationQuery,
  conversationsQuery,
  patchConversation,
  stopConversation,
  type ChatMessage,
  type ConversationDetail,
  type ModelSlot,
} from '@/lib/api'
import { takePendingPrompt } from '@/lib/pending'

export function ChatView({ conversation }: { conversation: ConversationDetail }) {
  const queryClient = useQueryClient()
  const [slot, setSlot] = useState<ModelSlot>(conversation.model_slot)

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
      void queryClient.invalidateQueries(conversationsQuery)
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
    await patchConversation(conversation.id, next)
    void queryClient.invalidateQueries(conversationQuery(conversation.id))
  }

  const handleStop = async () => {
    // The server persists the partial turn before it answers; then the fetch is released.
    await stopConversation(conversation.id).catch(() => undefined)
    await stop()
  }

  const streaming = status === 'streaming' || status === 'submitted'
  const lastMessage = messages.at(-1)

  return (
    <div className="flex h-full min-w-0 flex-1 flex-col">
      <header className="flex h-14 shrink-0 items-center justify-between gap-4 border-b px-6">
        <h1 className="truncate font-medium text-sm">{conversation.title}</h1>
        <span className="rounded-full border bg-muted/40 px-2.5 py-0.5 text-muted-foreground text-xs">
          {MODEL_SLOTS.find((m) => m.slot === slot)?.label} model
        </span>
      </header>

      <Conversation className="flex-1">
        <ConversationContent className="mx-auto w-full max-w-3xl gap-6 px-6 py-8">
          {messages.length === 0 && !streaming ? (
            <EmptyState onPick={(text) => void sendMessage({ text })} />
          ) : (
            messages.map((message) => (
              <TranscriptMessage
                isLast={message === lastMessage}
                key={message.id}
                message={message}
                streaming={streaming}
              />
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
          <Composer onSlotChange={changeSlot} onStop={handleStop} onSubmit={(text) => sendMessage({ text })} slot={slot} status={status} />
          <p className="pt-2 text-center text-[11px] text-muted-foreground">
            Numbers come from executed queries, never from the model.
          </p>
        </div>
      </div>
    </div>
  )
}

function thinkingMessage(isStreaming: boolean, duration?: number) {
  if (isStreaming) return <Shimmer duration={1}>Thinking...</Shimmer>
  if (duration === undefined) return <p>Thought for a moment</p>
  return <p>Thought for {duration === 1 ? '1 second' : `${duration} seconds`}</p>
}

type MessagePart = ChatMessage['parts'][number]

/** One turn can think several times in a row (a tool call ends a model response). One panel. */
function foldReasoning(parts: MessagePart[]): MessagePart[] {
  const folded: MessagePart[] = []
  for (const part of parts) {
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
}: {
  message: ChatMessage
  isLast: boolean
  streaming: boolean
}) {
  const interrupted = message.metadata?.interrupted === true
  return (
    <Message from={message.role}>
      <MessageContent>
        {foldReasoning(message.parts).map((part, index) => {
          if (part.type === 'reasoning') {
            const isStreaming = streaming && isLast && part.state === 'streaming'
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
          if (part.type === 'text') {
            return message.role === 'user' ? (
              <p className="whitespace-pre-wrap" key={`${message.id}-${index}`}>
                {part.text}
              </p>
            ) : (
              <MessageResponse isAnimating={streaming && isLast} key={`${message.id}-${index}`}>
                {part.text}
              </MessageResponse>
            )
          }
          return null
        })}
        {interrupted && (
          <span className="inline-flex w-fit items-center gap-1.5 rounded-full border border-dashed px-2.5 py-0.5 text-muted-foreground text-xs">
            <CircleStopIcon className="size-3" />
            Stopped
          </span>
        )}
      </MessageContent>
    </Message>
  )
}
