import { useQuery } from '@tanstack/react-query'
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

import { conversationsQuery, profilesQuery, type Conversation, type Profile } from '@/lib/api'

// What the browser remembers: the profile in use, its open tabs, and per conversation the
// scroll position and the unsent draft.
const ACTIVE_PROFILE_KEY = 'finquery-profile'
const tabsKey = (profileId: string) => `finquery-tabs:${profileId}`
const draftKey = (conversationId: string) => `finquery-draft:${conversationId}`
const scrollKey = (conversationId: string) => `finquery-scroll:${conversationId}`

function readIds(key: string): string[] {
  try {
    const raw = localStorage.getItem(key)
    const parsed = raw === null ? [] : (JSON.parse(raw) as unknown)
    return Array.isArray(parsed) ? parsed.filter((id): id is string => typeof id === 'string') : []
  } catch {
    return []
  }
}

export const readDraft = (conversationId: string) => localStorage.getItem(draftKey(conversationId)) ?? ''

export function writeDraft(conversationId: string, text: string) {
  if (text) localStorage.setItem(draftKey(conversationId), text)
  else localStorage.removeItem(draftKey(conversationId))
}

/** Undefined when this conversation was never scrolled: zero means the top, which is different. */
export function readScrollTop(conversationId: string): number | undefined {
  const stored = localStorage.getItem(scrollKey(conversationId))
  return stored === null ? undefined : Number(stored) || 0
}

export const writeScrollTop = (conversationId: string, top: number) =>
  localStorage.setItem(scrollKey(conversationId), String(Math.round(top)))

export function forgetConversation(conversationId: string) {
  localStorage.removeItem(draftKey(conversationId))
  localStorage.removeItem(scrollKey(conversationId))
}

interface Workspace {
  profiles: Profile[]
  profile: Profile | undefined
  /** The active profile's conversations, most recent activity first. */
  conversations: Conversation[]
  switchProfile: (profileId: string) => void
  /** Open conversations, in the order they were opened. */
  tabs: Conversation[]
  openTab: (conversationId: string) => void
  closeTab: (conversationId: string) => void
}

const WorkspaceContext = createContext<Workspace | null>(null)

export function useWorkspace(): Workspace {
  const workspace = useContext(WorkspaceContext)
  if (!workspace) throw new Error('useWorkspace must be used inside WorkspaceProvider')
  return workspace
}

/** Writes the tab list through on its way into state, so state and storage never disagree. */
function persisted(profileId: string, ids: string[]): string[] {
  localStorage.setItem(tabsKey(profileId), JSON.stringify(ids))
  return ids
}

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const { data: profiles } = useQuery(profilesQuery)
  const [activeId, setActiveId] = useState(() => localStorage.getItem(ACTIVE_PROFILE_KEY) ?? '')
  // A remembered profile can be gone (deleted here or in another tab), so fall back to the first.
  const profile = profiles?.find((p) => p.id === activeId) ?? profiles?.[0]

  const profileId = profile?.id
  const { data: conversations } = useQuery(conversationsQuery(profileId))
  const [tabIds, setTabIds] = useState<string[]>([])

  const openTab = useCallback(
    (conversationId: string) => {
      if (!profileId) return
      setTabIds((prev) => persisted(profileId, prev.includes(conversationId) ? prev : [...prev, conversationId]))
    },
    [profileId],
  )

  const closeTab = useCallback(
    (conversationId: string) => {
      if (!profileId) return
      setTabIds((prev) => persisted(profileId, prev.filter((id) => id !== conversationId)))
    },
    [profileId],
  )

  const switchProfile = useCallback((next: string) => {
    localStorage.setItem(ACTIVE_PROFILE_KEY, next)
    setActiveId(next)
  }, [])

  // Local storage is the source of truth for which tabs are open, per profile.
  useEffect(() => {
    setTabIds(profileId ? readIds(tabsKey(profileId)) : [])
  }, [profileId])

  const workspace = useMemo<Workspace>(() => {
    const byId = new Map((conversations ?? []).map((c) => [c.id, c]))
    return {
      closeTab,
      conversations: conversations ?? [],
      openTab,
      profile,
      profiles: profiles ?? [],
      switchProfile,
      // A tab whose conversation is gone (deleted in another browser tab) simply stops showing.
      tabs: tabIds.map((id) => byId.get(id)).filter((c): c is Conversation => c !== undefined),
    }
  }, [closeTab, conversations, openTab, profile, profiles, switchProfile, tabIds])

  return <WorkspaceContext.Provider value={workspace}>{children}</WorkspaceContext.Provider>
}
