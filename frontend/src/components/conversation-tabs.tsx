import { Link, useNavigate, useParams } from '@tanstack/react-router'
import { PlusIcon, XIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import { useWorkspace } from '@/lib/workspace'

/** Open conversations across the top. Each tab keeps its own scroll position and draft. */
export function ConversationTabs() {
  const { tabs, closeTab } = useWorkspace()
  const { conversationId } = useParams({ strict: false }) as { conversationId?: string }
  const navigate = useNavigate()

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

  return (
    <div className="flex h-10 shrink-0 items-center gap-1 overflow-x-auto border-b bg-sidebar px-2" role="tablist">
      {tabs.map((tab) => {
        const active = tab.id === conversationId
        return (
          <div
            className={cn(
              'group flex h-7 shrink-0 items-center rounded-md text-xs transition-colors',
              active
                ? 'border bg-background font-medium text-foreground shadow-xs'
                : 'text-muted-foreground hover:bg-sidebar-accent hover:text-foreground',
            )}
            key={tab.id}
          >
            <Link
              aria-selected={active}
              className="max-w-44 truncate py-1 pl-2.5"
              params={{ conversationId: tab.id }}
              role="tab"
              title={tab.title}
              to="/c/$conversationId"
            >
              {tab.title}
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
              <XIcon className="size-3" />
            </Button>
          </div>
        )
      })}
      <Tooltip>
        <TooltipTrigger asChild>
          <Button aria-label="New chat" asChild className="shrink-0" size="icon-xs" variant="ghost">
            <Link to="/">
              <PlusIcon className="size-3.5" />
            </Link>
          </Button>
        </TooltipTrigger>
        <TooltipContent>New chat</TooltipContent>
      </Tooltip>
    </div>
  )
}
