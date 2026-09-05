import { useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate, useParams } from '@tanstack/react-router'
import {
  BrainIcon,
  LayoutDashboardIcon,
  MessageSquareIcon,
  MoreHorizontalIcon,
  PencilIcon,
  PlusIcon,
  SettingsIcon,
  TableIcon,
  ThumbsUpIcon,
  Trash2Icon,
  UploadIcon,
} from 'lucide-react'
import { useState } from 'react'

import { ConfirmDialog } from '@/components/dialogs'
import { ProfileSwitcher } from '@/components/profile-switcher'
import { ThemeToggle } from '@/components/theme-toggle'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'
import { conversationsQuery, deleteConversation, patchConversation, type Conversation } from '@/lib/api'
import { cn } from '@/lib/utils'
import { forgetConversation, useWorkspace } from '@/lib/workspace'

/** Every row of the sidebar shares this inset, so the icons form one column under the New chat
 *  button's plus (which sits at the Button's px-2.5 behind a 1px border). */
const ROW = 'flex items-center gap-2 rounded-md px-2.5 py-1.5 text-sm transition-colors hover:bg-sidebar-accent focus-ring'
const ROW_ICON = 'size-4 shrink-0 text-muted-foreground'

const PAGES = [
  { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboardIcon, title: 'The charts this profile keeps' },
  { to: '/transactions', label: 'Transactions', icon: TableIcon },
  { to: '/import', label: 'Imports', icon: UploadIcon, title: 'What every file you dropped into a chat brought in' },
  { to: '/memory', label: 'Memory', icon: BrainIcon },
  { to: '/feedback', label: 'Feedback', icon: ThumbsUpIcon },
] as const

export function Brand({ className }: { className?: string }) {
  return (
    <div className={cn('flex items-center gap-2.5', className)}>
      <span className="flex size-7 items-center justify-center rounded-lg bg-primary text-primary-foreground shadow-sm">
        <svg aria-hidden="true" className="size-4" fill="none" viewBox="0 0 16 16">
          <path d="M2 12.5 6 8l3 3 5-6" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" />
          <path d="M10.5 5H14v3.5" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" />
        </svg>
      </span>
      <span className="font-heading font-semibold tracking-tight">FinQuery</span>
    </div>
  )
}

export function AppSidebar() {
  const { conversations, profile, closeTab } = useWorkspace()
  const params = useParams({ strict: false }) as { conversationId?: string }
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [renaming, setRenaming] = useState<string>()
  const [deleting, setDeleting] = useState<Conversation>()

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
    <aside className="flex h-full w-64 shrink-0 flex-col border-r bg-sidebar text-sidebar-foreground">
      <div className="flex h-14 items-center px-4">
        <Link className="rounded-lg focus-ring" to="/">
          <Brand />
        </Link>
      </div>

      <div className="flex flex-col gap-1 px-3 pb-2">
        <Button asChild className="w-full justify-start" variant="outline">
          <Link to="/">
            <PlusIcon data-icon="inline-start" />
            New chat
          </Link>
        </Button>
        {PAGES.map(({ to, label, icon: Icon, ...rest }) => (
          <Link activeProps={{ className: 'bg-sidebar-accent font-medium' }} className={ROW} key={to} to={to} {...rest}>
            <Icon className={ROW_ICON} />
            {label}
          </Link>
        ))}
      </div>

      <nav aria-label="Conversations" className="flex-1 overflow-y-auto px-3 py-2">
        {conversations.length > 0 ? (
          <>
            <p className="px-2.5 pb-2 font-medium text-2xs text-muted-foreground uppercase tracking-wider">Recent</p>
            <ul className="flex flex-col gap-0.5">
              {conversations.map((conversation) => (
                <li key={conversation.id}>
                  {renaming === conversation.id ? (
                    <Input
                      aria-label="Conversation title"
                      autoFocus
                      className="h-8 text-sm"
                      defaultValue={conversation.title}
                      onBlur={(event) => void rename(conversation, event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter') void rename(conversation, event.currentTarget.value)
                        if (event.key === 'Escape') setRenaming(undefined)
                      }}
                    />
                  ) : (
                    <div
                      className={cn(
                        'group flex items-center rounded-md transition-colors hover:bg-sidebar-accent',
                        params.conversationId === conversation.id && 'bg-sidebar-accent',
                      )}
                    >
                      <Link
                        className={cn(
                          'flex min-w-0 flex-1 items-center gap-2 rounded-md py-1.5 pl-2.5 text-sm focus-ring',
                          params.conversationId === conversation.id && 'font-medium',
                        )}
                        params={{ conversationId: conversation.id }}
                        title={conversation.running ? `${conversation.title} (answering)` : conversation.title}
                        to="/c/$conversationId"
                      >
                        {/* A chat answering a turn says so wherever the user is, because the
                            turn no longer needs anyone to be watching it (ticket 33). */}
                        {conversation.running ? (
                          <Spinner aria-label="Answering" className={ROW_ICON} />
                        ) : (
                          <MessageSquareIcon className={ROW_ICON} />
                        )}
                        <span className="truncate">{conversation.title}</span>
                      </Link>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button
                            aria-label={`Actions for ${conversation.title}`}
                            className="mr-1 opacity-0 transition-opacity focus-visible:opacity-100 group-hover:opacity-100 aria-expanded:opacity-100"
                            size="icon-xs"
                            variant="ghost"
                          >
                            <MoreHorizontalIcon />
                          </Button>
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
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </>
        ) : (
          <p className="px-2.5 py-6 text-center text-muted-foreground text-xs">Your conversations will appear here.</p>
        )}
      </nav>

      <div className="border-t p-2">
        <Button asChild className="w-full justify-start text-muted-foreground" size="sm" variant="ghost">
          <Link activeProps={{ className: 'bg-sidebar-accent text-foreground' }} to="/settings">
            <SettingsIcon data-icon="inline-start" />
            Settings
          </Link>
        </Button>
        <div className="mt-1 flex items-center gap-1">
          <div className="min-w-0 flex-1">
            <ProfileSwitcher />
          </div>
          <ThemeToggle />
        </div>
      </div>

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
    </aside>
  )
}
