import { useQueryClient } from '@tanstack/react-query'
import { Link, useLocation, useNavigate, useParams } from '@tanstack/react-router'
import {
  BrainIcon,
  LayoutDashboardIcon,
  MessageSquareIcon,
  MoreHorizontalIcon,
  PencilIcon,
  PlusIcon,
  SettingsIcon,
  TableIcon,
  Trash2Icon,
  UploadIcon,
} from 'lucide-react'
import { useState } from 'react'

import { ConfirmDialog } from '@/components/dialogs'
import { ProfileSwitcher } from '@/components/profile-switcher'
import { ThemeToggle } from '@/components/theme-toggle'
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

/** The brand mark and the name. The mark is 32px so it fills the icon rail's square exactly. */
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
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton asChild size="lg" tooltip="FinQuery">
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
        <SidebarGroup>
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
        <SidebarGroup className="group-data-[collapsible=icon]:hidden">
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
              <p className="px-2 py-6 text-center text-muted-foreground text-xs">Your conversations will appear here.</p>
            )}
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton asChild className={ROW} isActive={pathname === '/settings'} tooltip="Settings">
              <Link onClick={followed} to="/settings">
                <SettingsIcon />
                <span>Settings</span>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
        {/* Side by side when there is room, one under the other in the rail. */}
        <div className="flex items-center gap-1 group-data-[collapsible=icon]:flex-col">
          <ProfileSwitcher />
          <ThemeToggle />
        </div>
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
