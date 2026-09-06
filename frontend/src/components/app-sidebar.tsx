import { useQueryClient } from '@tanstack/react-query'
import { Link, useLocation, useNavigate, useParams } from '@tanstack/react-router'
import {
  BrainIcon,
  LayoutDashboardIcon,
  MessageSquareIcon,
  MoonIcon,
  MoreHorizontalIcon,
  PencilIcon,
  PlusIcon,
  SettingsIcon,
  SunIcon,
  TableIcon,
  Trash2Icon,
  UploadIcon,
} from 'lucide-react'
import { useState } from 'react'

import { ConfirmDialog } from '@/components/dialogs'
import { ProfileSwitcher } from '@/components/profile-switcher'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInput,
  SidebarMenu,
  SidebarMenuAction,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
} from '@/components/ui/sidebar'
import { Spinner } from '@/components/ui/spinner'
import { useSidebar } from '@/hooks/use-sidebar'
import { conversationsQuery, deleteConversation, patchConversation, type Conversation } from '@/lib/api'
import { useTheme } from '@/lib/theme'
import { forgetConversation, useWorkspace } from '@/lib/workspace'

/** Navigation is quiet: a row is muted until it is hovered or active, when the component gives
 *  it the faint tint and the full foreground. No accent colour anywhere in the navigation. */
const ROW = 'text-muted-foreground'

const PAGES = [
  { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboardIcon, title: 'The charts this profile keeps' },
  { to: '/transactions', label: 'Transactions', icon: TableIcon },
  { to: '/import', label: 'Imports', icon: UploadIcon, title: 'What every file you dropped into a chat brought in' },
  { to: '/memory', label: 'Memory', icon: BrainIcon },
] as const

/** The brand mark and the name. The mark is 32px: it fills the icon rail's square exactly, and
 *  it is the height of every other row, so the brand row is an h-8 row like the rest. */
function Brand() {
  return (
    <>
      <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground shadow-sm">
        <svg aria-hidden="true" className="size-4" fill="none" viewBox="0 0 16 16">
          <path d="M2 12.5 6 8l3 3 5-6" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" />
          <path d="M10.5 5H14v3.5" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" />
        </svg>
      </span>
      <span className="truncate font-heading font-semibold tracking-tight">FinQuery</span>
    </>
  )
}

export function AppSidebar() {
  const { conversations, profile, closeTab } = useWorkspace()
  const params = useParams({ strict: false }) as { conversationId?: string }
  const pathname = useLocation({ select: (location) => location.pathname })
  const { isMobile, setOpenMobile, state } = useSidebar()
  const { theme, toggle: toggleTheme } = useTheme()
  const themeLabel = theme === 'dark' ? 'Light theme' : 'Dark theme'
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [renaming, setRenaming] = useState<string>()
  const [deleting, setDeleting] = useState<Conversation>()

  // On a phone the sidebar is a sheet over the page, so following a link closes it.
  const followed = () => {
    if (isMobile) setOpenMobile(false)
  }

  const refresh = () => queryClient.invalidateQueries(conversationsQuery(profile?.id))

  const rename = async (conversation: Conversation, title: string) => {
    setRenaming(undefined)
    if (!title.trim() || title.trim() === conversation.title) return
    await patchConversation(conversation.id, { title: title.trim() })
    await refresh()
    await queryClient.invalidateQueries({ queryKey: ['conversation', conversation.id] })
  }

  const remove = async (conversation: Conversation) => {
    // Leave it before it is gone, so nothing tries to render a deleted conversation.
    if (params.conversationId === conversation.id) await navigate({ to: '/' })
    await deleteConversation(conversation.id)
    closeTab(conversation.id)
    forgetConversation(conversation.id)
    await refresh()
  }

  return (
    <Sidebar collapsible="icon">
      {/* Two h-8 rows on the header's own padding and gap: 8 + 32 + 8 + 32 + 8 = 88, the height
          of the tabs strip (h-10) and the page bar (h-12) together, so the brand row ends on the
          strip's hairline and New chat is centred on the page title. `size="lg"` keeps the rail's
          unpadded square for the 32px mark; `h-8 p-0` gives the expanded row the height of every
          other row, with the mark on the icon axis. */}
      <SidebarHeader className="px-4 pt-3 pb-2 group-data-[collapsible=icon]:px-2">
        <SidebarMenu className="gap-3">
          <SidebarMenuItem>
            <SidebarMenuButton asChild className="h-8 p-0" size="lg" tooltip="FinQuery">
              <Link onClick={followed} to="/">
                <Brand />
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
          <SidebarMenuItem>
            {/* The primary action: the one bordered row, so it reads as a button, not a page. */}
            <SidebarMenuButton asChild tooltip="New chat" variant="outline">
              <Link onClick={followed} to="/">
                <PlusIcon className="text-primary" />
                <span>New chat</span>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup className="px-4 pt-4 group-data-[collapsible=icon]:px-2">
          <SidebarGroupContent>
            <SidebarMenu>
              {PAGES.map((page) => (
                <SidebarMenuItem key={page.to}>
                  <SidebarMenuButton asChild className={ROW} isActive={pathname === page.to} tooltip={page.label}>
                    {/* In the rail the tooltip names the page, so the longer title waits for
                        the expanded sidebar or the two would show together. */}
                    <Link
                      onClick={followed}
                      title={state === 'expanded' && 'title' in page ? page.title : undefined}
                      to={page.to}
                    >
                      <page.icon />
                      <span>{page.label}</span>
                    </Link>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        {/* The rail has no room for titles, so this whole group folds away with it. */}
        <SidebarGroup className="px-4 group-data-[collapsible=icon]:hidden">
          <SidebarGroupLabel>Recent</SidebarGroupLabel>
          <SidebarGroupContent>
            {conversations.length > 0 ? (
              <SidebarMenu aria-label="Conversations">
                {conversations.map((conversation) => (
                  <SidebarMenuItem key={conversation.id}>
                    {renaming === conversation.id ? (
                      <SidebarInput
                        aria-label="Conversation title"
                        autoFocus
                        defaultValue={conversation.title}
                        onBlur={(event) => void rename(conversation, event.target.value)}
                        onKeyDown={(event) => {
                          if (event.key === 'Enter') void rename(conversation, event.currentTarget.value)
                          if (event.key === 'Escape') setRenaming(undefined)
                        }}
                      />
                    ) : (
                      <>
                        <SidebarMenuButton asChild className={ROW} isActive={params.conversationId === conversation.id}>
                          <Link
                            onClick={followed}
                            params={{ conversationId: conversation.id }}
                            title={conversation.running ? `${conversation.title} (answering)` : conversation.title}
                            to="/c/$conversationId"
                          >
                            {/* A chat answering a turn says so wherever the user is, because the
                                turn no longer needs anyone to be watching it (ticket 33). */}
                            {conversation.running ? <Spinner aria-label="Answering" /> : <MessageSquareIcon />}
                            <span>{conversation.title}</span>
                          </Link>
                        </SidebarMenuButton>
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <SidebarMenuAction aria-label={`Actions for ${conversation.title}`} showOnHover>
                              <MoreHorizontalIcon />
                            </SidebarMenuAction>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end" className="w-40">
                            <DropdownMenuItem onSelect={() => setRenaming(conversation.id)}>
                              <PencilIcon />
                              Rename
                            </DropdownMenuItem>
                            <DropdownMenuItem onSelect={() => setDeleting(conversation)} variant="destructive">
                              <Trash2Icon />
                              Delete
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </>
                    )}
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            ) : (
              // A row where the first conversation will be, on the rows' own inset and height.
              <p className="flex h-8 items-center px-2 text-muted-foreground text-xs">
                Your conversations will appear here.
              </p>
            )}
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      {/* Three rows of one menu, like the pages above: the same height, inset and gap, and in the
          rail three squares in one column. The theme row names the theme it switches to. */}
      <SidebarFooter className="px-4 group-data-[collapsible=icon]:px-2">
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton asChild className={ROW} isActive={pathname === '/settings'} tooltip="Settings">
              <Link onClick={followed} to="/settings">
                <SettingsIcon />
                <span>Settings</span>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
          <SidebarMenuItem>
            <SidebarMenuButton
              aria-label={`Switch to ${themeLabel.toLowerCase()}`}
              className={ROW}
              onClick={toggleTheme}
              tooltip={themeLabel}
            >
              {theme === 'dark' ? <SunIcon /> : <MoonIcon />}
              <span>{themeLabel}</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
          <SidebarMenuItem>
            <ProfileSwitcher />
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
      <SidebarRail />

      <ConfirmDialog
        action="Delete chat"
        description={`"${deleting?.title ?? ''}" and everything in it is deleted. This cannot be undone.`}
        onConfirm={async () => {
          if (deleting) await remove(deleting)
        }}
        onOpenChange={(open) => setDeleting(open ? deleting : undefined)}
        open={deleting !== undefined}
        title="Delete this chat?"
      />
    </Sidebar>
  )
}
