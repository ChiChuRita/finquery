import { Link, useNavigate, useParams } from '@tanstack/react-router'
import { PlusIcon, XIcon } from 'lucide-react'
import { useEffect, useRef } from 'react'

import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import { useWorkspace } from '@/lib/workspace'

/** Open conversations across the top. Each tab keeps its own scroll position and draft. */
export function ConversationTabs() {
  const { tabs, closeTab } = useWorkspace()
  const { conversationId } = useParams({ strict: false }) as { conversationId?: string }
  const navigate = useNavigate()
  const current = useRef<HTMLDivElement>(null)

  // Past a dozen or so the bar scrolls, and the tab in front is then usually outside it: at
  // thirty tabs the bar showed the oldest ones and nothing said which chat was open. The tab
  // list arrives after the first render (local storage is read in an effect), so the count is
  // part of the signal or a reload never scrolls at all.
  useEffect(() => {
    current.current?.scrollIntoView({ block: 'nearest', inline: 'nearest' })
  }, [conversationId, tabs.length])

  if (tabs.length === 0) return null

  const close = async (id: string) => {
    if (id !== conversationId) {
      closeTab(id)
      return
    }
    const next = tabs.filter((tab) => tab.id !== id).at(-1)
    closeTab(id)
    await (next ? navigate({ to: '/c/$conversationId', params: { conversationId: next.id } }) : navigate({ to: '/' }))
  }

  // Each tab is a link to a route, so this is navigation, not an ARIA tablist: a tablist may hold
  // nothing but tabs, and the close buttons and the New chat link in here were the one axe
  // violation on every page.
  return (
    <nav
      aria-label="Open conversations"
      className="flex h-10 shrink-0 items-center gap-1 overflow-x-auto border-b px-2"
    >
      {tabs.map((tab) => {
        const active = tab.id === conversationId
        // The strip sits on the canvas, so the open tab is marked the way the sidebar marks its
        // active row: the faint tint and the full foreground, no border of its own.
        return (
          <div
            className={cn(
              'group flex h-7 shrink-0 items-center rounded-md text-xs transition-colors',
              active
                ? 'bg-sidebar-accent font-medium text-foreground'
                : 'text-muted-foreground hover:bg-sidebar-accent hover:text-foreground',
            )}
            key={tab.id}
            ref={active ? current : undefined}
          >
            <Link
              aria-current={active ? 'page' : undefined}
              className="flex max-w-44 items-center gap-1.5 rounded-md py-1 pl-2.5 focus-ring"
              params={{ conversationId: tab.id }}
              title={tab.running ? `${tab.title} (answering)` : tab.title}
              to="/c/$conversationId"
            >
              {/* A turn of that chat is running, wherever the user happens to be looking. */}
              {tab.running && <Spinner aria-label="Answering" className="size-3 shrink-0 text-muted-foreground" />}
              <span className="truncate">{tab.title}</span>
            </Link>
            <Button
              aria-label={`Close ${tab.title}`}
              className={cn(
                'mx-0.5 opacity-0 transition-opacity focus-visible:opacity-100 group-hover:opacity-100',
                active && 'opacity-60',
              )}
              onClick={() => void close(tab.id)}
              size="icon-xs"
              variant="ghost"
            >
              <XIcon />
            </Button>
          </div>
        )
      })}
      {/* Sticky, so it is still reachable once the tabs have filled the bar. */}
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            aria-label="New chat"
            asChild
            className="sticky right-0 shrink-0 bg-background"
            size="icon-xs"
            variant="ghost"
          >
            <Link to="/">
              <PlusIcon />
            </Link>
          </Button>
        </TooltipTrigger>
        <TooltipContent>New chat</TooltipContent>
      </Tooltip>
    </nav>
  )
}
