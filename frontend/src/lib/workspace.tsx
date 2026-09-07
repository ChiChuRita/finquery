import { useQuery } from '@tanstack/react-query'
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

import { conversationsQuery, profilesQuery, type Conversation, type Profile } from '@/lib/api'

// What the browser remembers: the profile in use, the conversation each profile was last in,
// and per conversation the scroll position and the unsent draft.
const ACTIVE_PROFILE_KEY = 'finquery-profile'
// The stored name is older than this key's job (it held the tab that was in front) and is kept
// so a browser that has one keeps its memory.
const lastConversationKey = (profileId: string) => `finquery-tab:${profileId}`
const draftKey = (conversationId: string) => `finquery-draft:${conversationId}`
const scrollKey = (conversationId: string) => `finquery-scroll:${conversationId}`

/** The profile the browser was left in, read before the first query goes out.
 *
 * Empty when this browser has never chosen one, which is a first visit or a storage another
 * origin wrote (127.0.0.1 and localhost are two). The provider then falls back to the first
 * profile and writes that back, so what is on screen and what is remembered never disagree.
 */
function readActiveProfile(): string {
  try {
    return localStorage.getItem(ACTIVE_PROFILE_KEY) ?? ''
  } catch {
    return ''
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

/** The conversation to go back to, if this profile was ever in one.
 *
 * Nothing here says it still exists: it can have been deleted in another browser tab or in
 * another window of this one. Opening it is how that is found out, so the conversation route
 * sends a conversation the server does not have to the new chat page.
 */
export function readLastConversation(profileId: string): string | undefined {
  return localStorage.getItem(lastConversationKey(profileId)) ?? undefined
}

interface Workspace {
  profiles: Profile[]
  profile: Profile | undefined
  /** The active profile's conversations, most recent activity first. */
  conversations: Conversation[]
  switchProfile: (profileId: string) => void
  /** Note this conversation as the profile's last, for the next time the profile is picked. */
  rememberLastConversation: (conversationId: string) => void
}

const WorkspaceContext = createContext<Workspace | null>(null)

export function useWorkspace(): Workspace {
  const workspace = useContext(WorkspaceContext)
  if (!workspace) throw new Error('useWorkspace must be used inside WorkspaceProvider')
  return workspace
}

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const { data: profiles } = useQuery(profilesQuery)
  const [activeId, setActiveId] = useState(readActiveProfile)
  // A remembered profile can be gone (deleted here or in another tab), so fall back to the first.
  // Until the list is here there is no profile at all: a query that would run against the wrong
  // one is better not run, which is what every `enabled: profileId !== undefined` is about.
  const profile = profiles?.find((p) => p.id === activeId) ?? profiles?.[0]

  const profileId = profile?.id
  const { data: conversations } = useQuery(conversationsQuery(profileId))

  const rememberLastConversation = useCallback(
    (conversationId: string) => {
      if (profileId) localStorage.setItem(lastConversationKey(profileId), conversationId)
    },
    [profileId],
  )

  const switchProfile = useCallback((next: string) => {
    localStorage.setItem(ACTIVE_PROFILE_KEY, next)
    setActiveId(next)
  }, [])

  // The fallback is a choice, so it is written down like any other: what is done after a reload
  // lands in the profile the sidebar names, and the next reload opens that same one again.
  useEffect(() => {
    if (profile && profile.id !== activeId) switchProfile(profile.id)
  }, [activeId, profile, switchProfile])

  const workspace = useMemo<Workspace>(
    () => ({
      conversations: conversations ?? [],
      profile,
      profiles: profiles ?? [],
      rememberLastConversation,
      switchProfile,
    }),
    [conversations, profile, profiles, rememberLastConversation, switchProfile],
  )

  return <WorkspaceContext.Provider value={workspace}>{children}</WorkspaceContext.Provider>
}
