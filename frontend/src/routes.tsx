import { useQuery, useQueryClient } from '@tanstack/react-query'
import { createRootRoute, createRoute, createRouter, Outlet, useNavigate } from '@tanstack/react-router'
import { useState } from 'react'

import { AppSidebar } from '@/components/app-sidebar'
import { ChatView } from '@/components/chat-view'
import { Composer } from '@/components/composer'
import { EmptyState } from '@/components/empty-state'
import { Shimmer } from '@/components/ai-elements/shimmer'
import { conversationQuery, conversationsQuery, createConversation, type ModelSlot } from '@/lib/api'
import { stashPendingPrompt } from '@/lib/pending'

const rootRoute = createRootRoute({
  component: () => (
    <div className="flex h-dvh w-full overflow-hidden bg-background">
      <AppSidebar />
      <main className="flex min-w-0 flex-1 flex-col">
        <Outlet />
      </main>
    </div>
  ),
})

function NewChatPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [slot, setSlot] = useState<ModelSlot>('fast')
  const [creating, setCreating] = useState(false)

  const start = async (text: string) => {
    if (creating) return
    setCreating(true)
    try {
      const conversation = await createConversation(slot)
      stashPendingPrompt(conversation.id, text)
      void queryClient.invalidateQueries(conversationsQuery)
      await navigate({ to: '/c/$conversationId', params: { conversationId: conversation.id } })
    } finally {
      setCreating(false)
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-1 flex-col items-center justify-center px-6">
        <div className="w-full max-w-3xl">
          <EmptyState onPick={start} />
          <Composer autoFocus onSlotChange={setSlot} onSubmit={start} slot={slot} status={creating ? 'submitted' : 'ready'} />
        </div>
      </div>
      <p className="pb-5 text-center text-[11px] text-muted-foreground">
        Numbers come from executed queries, never from the model.
      </p>
    </div>
  )
}

const indexRoute = createRoute({ getParentRoute: () => rootRoute, path: '/', component: NewChatPage })

function ConversationPage() {
  const { conversationId } = conversationRoute.useParams()
  const { data, error, isPending } = useQuery(conversationQuery(conversationId))

  if (isPending) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <Shimmer className="text-sm">Loading conversation...</Shimmer>
      </div>
    )
  }
  if (error || !data) {
    return (
      <div className="flex flex-1 items-center justify-center text-muted-foreground text-sm" role="alert">
        This conversation could not be loaded.
      </div>
    )
  }
  // Key on the id so a fresh useChat is mounted with the persisted transcript for each conversation.
  return <ChatView conversation={data} key={data.id} />
}

const conversationRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/c/$conversationId',
  component: ConversationPage,
})

export const router = createRouter({ routeTree: rootRoute.addChildren([indexRoute, conversationRoute]) })

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}
