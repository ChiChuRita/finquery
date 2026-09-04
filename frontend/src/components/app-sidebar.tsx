import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from '@tanstack/react-router'
import { MessageSquareIcon, PlusIcon } from 'lucide-react'

import { ThemeToggle } from '@/components/theme-toggle'
import { Button } from '@/components/ui/button'
import { conversationsQuery } from '@/lib/api'
import { cn } from '@/lib/utils'

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
  const { data: conversations } = useQuery(conversationsQuery)
  const params = useParams({ strict: false }) as { conversationId?: string }

  return (
    <aside className="flex h-full w-64 shrink-0 flex-col border-r bg-sidebar text-sidebar-foreground">
      <div className="flex h-14 items-center px-4">
        <Link to="/">
          <Brand />
        </Link>
      </div>

      <div className="px-3 pb-2">
        <Button asChild className="w-full justify-start gap-2" variant="outline">
          <Link to="/">
            <PlusIcon className="size-4" />
            New chat
          </Link>
        </Button>
      </div>

      <nav aria-label="Conversations" className="flex-1 overflow-y-auto px-3 py-2">
        {conversations && conversations.length > 0 ? (
          <>
            <p className="px-2 pb-2 font-medium text-[11px] text-muted-foreground uppercase tracking-wider">Recent</p>
            <ul className="flex flex-col gap-0.5">
              {conversations.map((c) => (
                <li key={c.id}>
                  <Link
                    className={cn(
                      'flex items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors hover:bg-sidebar-accent',
                      params.conversationId === c.id && 'bg-sidebar-accent font-medium',
                    )}
                    params={{ conversationId: c.id }}
                    title={c.title}
                    to="/c/$conversationId"
                  >
                    <MessageSquareIcon className="size-3.5 shrink-0 text-muted-foreground" />
                    <span className="truncate">{c.title}</span>
                  </Link>
                </li>
              ))}
            </ul>
          </>
        ) : (
          <p className="px-2 py-6 text-center text-muted-foreground text-xs">Your conversations will appear here.</p>
        )}
      </nav>

      <div className="flex items-center justify-between border-t px-3 py-2">
        <span className="px-1 text-muted-foreground text-xs">Default profile</span>
        <ThemeToggle />
      </div>
    </aside>
  )
}
