import { useQuery, useQueryClient } from '@tanstack/react-query'
import { createRootRoute, createRoute, createRouter, Link, Outlet, useNavigate } from '@tanstack/react-router'
import type { FileUIPart } from 'ai'
import { PlusIcon } from 'lucide-react'
import { useEffect, useState } from 'react'

import { Shimmer } from '@/components/ai-elements/shimmer'
import { AppSidebar } from '@/components/app-sidebar'
import { ChatView } from '@/components/chat-view'
import { Composer } from '@/components/composer'
import { ConversationTabs } from '@/components/conversation-tabs'
import { DashboardPage } from '@/components/dashboard-page'
import { EmptyState } from '@/components/empty-state'
import { FeedbackPage } from '@/components/feedback-page'
import { ImportPage } from '@/components/import-page'
import { MemoryPage } from '@/components/memory-page'
import { ModelsCard } from '@/components/models-card'
import { clampStep, OnboardingCard, OnboardingPage } from '@/components/onboarding'
import { DocumentPage } from '@/components/page'
import { TaxonomyCard } from '@/components/taxonomy-card'
import { TransactionsPage } from '@/components/transactions-page'
import { Button } from '@/components/ui/button'
import { WebLookupCard } from '@/components/web-lookup-card'
import {
  conversationQuery,
  conversationsQuery,
  createConversation,
  settingsQuery,
  type ModelSlot,
} from '@/lib/api'
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
  const { data: settings } = useQuery(settingsQuery(profile?.id))
  const [slot, setSlot] = useState<ModelSlot>()
  const [creating, setCreating] = useState(false)
  // Until the user picks one for this chat, a new conversation starts on the profile's default.
  const chosen = slot ?? settings?.default_model_slot ?? 'fast'

  // A profile that has never seen the setup opens it instead of an empty chat, once.
  const pending = settings?.onboarding_state === 'not_started'
  useEffect(() => {
    if (pending) void navigate({ to: '/onboarding', search: { step: 1 }, replace: true })
  }, [navigate, pending])

  const start = async (text: string, files: FileUIPart[] = []) => {
    if (creating || !profile) return
    setCreating(true)
    try {
      const conversation = await createConversation(profile.id, chosen)
      stashPendingPrompt(conversation.id, { text: text || undefined, files })
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
          <EmptyState onPick={(text) => void start(text)} />
          <Composer
            autoFocus
            onSlotChange={setSlot}
            onSubmit={start}
            slot={chosen}
            status={creating ? 'submitted' : 'ready'}
          />
        </div>
      </div>
      <p className="pb-5 text-center text-2xs text-muted-foreground">
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
    // Most often it was deleted in another browser tab, which is why this says what to do
    // rather than only what went wrong: without the link the tab is a dead end.
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-3 text-sm" role="alert">
        <p className="text-muted-foreground">This chat could not be loaded. It may have been deleted.</p>
        <Button asChild size="sm" variant="outline">
          <Link to="/">
            <PlusIcon data-icon="inline-start" />
            New chat
          </Link>
        </Button>
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

/** An ISO day, or nothing at all. Anything else in the URL is read as no bound rather than
 *  sent to the server: the range ends up in a WHERE clause, so only a real day may get there. */
const isoDay = (value: unknown) =>
  typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value) ? value : undefined

// The range is in the search params, so a reload, the back button and a shared link all show
// the same days. No parameter at all means the whole history.
const dashboardRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/dashboard',
  validateSearch: (search: Record<string, unknown>) => ({
    from: isoDay(search.from),
    to: isoDay(search.to),
  }),
  component: DashboardPage,
})

const importRoute = createRoute({ getParentRoute: () => rootRoute, path: '/import', component: ImportPage })

const memoryRoute = createRoute({ getParentRoute: () => rootRoute, path: '/memory', component: MemoryPage })

const feedbackRoute = createRoute({ getParentRoute: () => rootRoute, path: '/feedback', component: FeedbackPage })

const transactionsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/transactions',
  component: TransactionsPage,
})

function SettingsPage() {
  return (
    <DocumentPage description="How FinQuery runs on this machine." title="Settings">
      <OnboardingCard />
      <TaxonomyCard />
      <ModelsCard />
      <WebLookupCard />
    </DocumentPage>
  )
}

const settingsRoute = createRoute({ getParentRoute: () => rootRoute, path: '/settings', component: SettingsPage })

// The step is a search parameter, so a reload resumes where the user was.
const onboardingRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/onboarding',
  validateSearch: (search: Record<string, unknown>) => ({ step: clampStep(search.step) }),
  component: function OnboardingRoute() {
    const { step } = onboardingRoute.useSearch()
    return <OnboardingPage step={step} />
  },
})

export const router = createRouter({
  routeTree: rootRoute.addChildren([
    indexRoute,
    conversationRoute,
    dashboardRoute,
    importRoute,
    transactionsRoute,
    memoryRoute,
    feedbackRoute,
    settingsRoute,
    onboardingRoute,
  ]),
})

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}
