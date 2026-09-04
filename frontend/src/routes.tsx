import { useQuery, useQueryClient } from '@tanstack/react-query'
import { createRootRoute, createRoute, createRouter, Outlet, useNavigate } from '@tanstack/react-router'
import { useEffect, useState } from 'react'

import { Shimmer } from '@/components/ai-elements/shimmer'
import { AppSidebar } from '@/components/app-sidebar'
import { ChatView } from '@/components/chat-view'
import { Composer } from '@/components/composer'
import { ConversationTabs } from '@/components/conversation-tabs'
import { EmptyState } from '@/components/empty-state'
import { ImportPage } from '@/components/import-page'
import { MemoryPage } from '@/components/memory-page'
import { ModelsCard } from '@/components/models-card'
import { TransactionsPage } from '@/components/transactions-page'
import { conversationQuery, conversationsQuery, createConversation, type ModelSlot } from '@/lib/api'
import { stashPendingPrompt } from '@/lib/pending'
import { useWorkspace, WorkspaceProvider } from '@/lib/workspace'

const rootRoute = createRootRoute({
  component: () => (
    <WorkspaceProvider>
      <div className="flex h-dvh w-full overflow-hidden bg-background">
        <AppSidebar />
        <main className="flex min-w-0 flex-1 flex-col">
          <ConversationTabs />
          <Outlet />
        </main>
      </div>
    </WorkspaceProvider>
  ),
})

function NewChatPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { profile } = useWorkspace()
  const [slot, setSlot] = useState<ModelSlot>('fast')
  const [creating, setCreating] = useState(false)

  const start = async (text: string) => {
    if (creating || !profile) return
    setCreating(true)
    try {
      const conversation = await createConversation(profile.id, slot)
      stashPendingPrompt(conversation.id, text)
      void queryClient.invalidateQueries(conversationsQuery(profile.id))
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
  const { openTab, profile, switchProfile } = useWorkspace()

  useEffect(() => {
    if (!data) return
    // Opening a conversation of another profile (a bookmark, a reload) switches the sidebar to it.
    if (profile && data.profile_id !== profile.id) switchProfile(data.profile_id)
    else openTab(data.id)
  }, [data, openTab, profile, switchProfile])

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

const importRoute = createRoute({ getParentRoute: () => rootRoute, path: '/import', component: ImportPage })

const memoryRoute = createRoute({ getParentRoute: () => rootRoute, path: '/memory', component: MemoryPage })

const transactionsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/transactions',
  component: TransactionsPage,
})

function SettingsPage() {
  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto w-full max-w-3xl px-6 py-10">
        <h1 className="font-heading font-semibold text-2xl tracking-tight">Settings</h1>
        <p className="mt-1 text-muted-foreground text-sm">How FinQuery runs on this machine.</p>
        <div className="mt-6">
          <ModelsCard />
        </div>
      </div>
    </div>
  )
}

const settingsRoute = createRoute({ getParentRoute: () => rootRoute, path: '/settings', component: SettingsPage })

export const router = createRouter({
  routeTree: rootRoute.addChildren([
    indexRoute,
    conversationRoute,
    importRoute,
    transactionsRoute,
    memoryRoute,
    settingsRoute,
  ]),
})

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}
