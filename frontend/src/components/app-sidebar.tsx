import { useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate, useParams } from '@tanstack/react-router'
import {
  BrainIcon,
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
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { conversationsQuery, deleteConversation, patchConversation, type Conversation } from '@/lib/api'
import { cn } from '@/lib/utils'
import { forgetConversation, useWorkspace } from '@/lib/workspace'

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
        <Link to="/">
          <Brand />
        </Link>
      </div>

      <div className="space-y-1 px-3 pb-2">
        <Button asChild className="w-full justify-start gap-2" variant="outline">
          <Link to="/">
            <PlusIcon className="size-4" />
            New chat
          </Link>
        </Button>
        <Link
          activeProps={{ className: 'bg-sidebar-accent font-medium' }}
          className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors hover:bg-sidebar-accent"
          to="/transactions"
        >
          <TableIcon className="size-3.5 shrink-0 text-muted-foreground" />
          Transactions
        </Link>
        <Link
          activeProps={{ className: 'bg-sidebar-accent font-medium' }}
          className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors hover:bg-sidebar-accent"
          to="/import"
        >
          <UploadIcon className="size-3.5 shrink-0 text-muted-foreground" />
          Import
        </Link>
        <Link
          activeProps={{ className: 'bg-sidebar-accent font-medium' }}
          className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors hover:bg-sidebar-accent"
          to="/memory"
        >
          <BrainIcon className="size-3.5 shrink-0 text-muted-foreground" />
          Memory
        </Link>
      </div>

      <nav aria-label="Conversations" className="flex-1 overflow-y-auto px-3 py-2">
        {conversations.length > 0 ? (
          <>
            <p className="px-2 pb-2 font-medium text-[11px] text-muted-foreground uppercase tracking-wider">Recent</p>
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
                          'min-w-0 flex-1 flex items-center gap-2 py-1.5 pl-2 text-sm',
                          params.conversationId === conversation.id && 'font-medium',
                        )}
                        params={{ conversationId: conversation.id }}
                        title={conversation.title}
                        to="/c/$conversationId"
                      >
                        <MessageSquareIcon className="size-3.5 shrink-0 text-muted-foreground" />
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
                            <MoreHorizontalIcon className="size-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end" className="w-40">
                          <DropdownMenuItem onSelect={() => setRenaming(conversation.id)}>
                            <PencilIcon className="size-4" />
                            Rename
                          </DropdownMenuItem>
                          <DropdownMenuItem onSelect={() => setDeleting(conversation)} variant="destructive">
                            <Trash2Icon className="size-4" />
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
          <p className="px-2 py-6 text-center text-muted-foreground text-xs">Your conversations will appear here.</p>
        )}
      </nav>

      <div className="border-t p-2">
        <Button asChild className="w-full justify-start gap-2 text-muted-foreground" size="sm" variant="ghost">
          <Link activeProps={{ className: 'bg-sidebar-accent text-foreground' }} to="/settings">
            <SettingsIcon className="size-3.5" />
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
