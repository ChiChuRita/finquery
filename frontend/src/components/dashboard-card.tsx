import { Link } from '@tanstack/react-router'
import {
  ChevronLeftIcon,
  ChevronRightIcon,
  MoreHorizontalIcon,
  PencilIcon,
  RefreshCwIcon,
  Trash2Icon,
} from 'lucide-react'
import { useState } from 'react'

import {
  ChartCard,
  ChartCardHeader,
  ChartFrame,
  FailedBody,
  failureLine,
  Footer,
} from '@/components/chart-tool'
import { ConfirmDialog } from '@/components/dialogs'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { CHART_HEIGHT, type ChartLanguage } from '@/lib/chart-frame'
import type { ChartToolOutput, DashboardChart } from '@/lib/api'
import { formatDateTime } from '@/lib/format'

/** A card with nothing to draw. Two different nothings, so two different sentences. */
function NoRows({ hasData }: { hasData: boolean }) {
  return (
    <div
      className="flex flex-col items-center justify-center gap-2 px-6 text-center"
      style={{ height: CHART_HEIGHT }}
    >
      {hasData ? (
        <p className="text-muted-foreground text-sm">
          The query behind this chart returns no rows right now, so there is nothing to draw.
        </p>
      ) : (
        <>
          <p className="text-muted-foreground text-sm">
            This chart fills itself as soon as the profile has bookings.
          </p>
          <Button asChild size="sm" variant="outline">
            <Link to="/">Drop a statement into a chat</Link>
          </Button>
        </>
      )}
    </div>
  )
}

/** The chart of a card, or the one line that says why there is none.
 *
 * The frame is never given an empty array: a mark over no rows throws, and a card that says so
 * in a sentence is the whole point of re-running the statement on every load.
 */
function CardBody({
  chart,
  hasData,
  title,
}: {
  chart: DashboardChart | ChartToolOutput
  hasData: boolean
  title: string
}) {
  if (chart.error) {
    return (
      <div className="px-4 pb-3">
        <FailedBody
          hint="The whole reason, the plan and the query it ran are under Details."
          reason={failureLine(chart.error)}
        />
      </div>
    )
  }
  if (!chart.code || chart.rows.length === 0) return <NoRows hasData={hasData} />
  return (
    <ChartFrame
      code={chart.code}
      language={(chart.language ?? 'en') as ChartLanguage}
      rows={chart.rows}
      title={title}
    />
  )
}

/** One stored card: the drawing, and the five things that can be done to it.
 *
 * Nothing here regenerates the chart. The definition is the one that was checked when the card
 * was made; only the numbers under it are new, which is what Refresh says out loud.
 */
export function DashboardCard({
  card,
  hasData,
  first,
  last,
  onRename,
  onMove,
  onRefresh,
  onRemove,
  busy = false,
}: {
  card: DashboardChart
  hasData: boolean
  first: boolean
  last: boolean
  onRename: (title: string) => Promise<void> | void
  onMove: (position: number) => Promise<void> | void
  onRefresh: () => Promise<void> | void
  onRemove: () => Promise<void> | void
  busy?: boolean
}) {
  const [renaming, setRenaming] = useState(false)
  const [removing, setRemoving] = useState(false)

  const rename = (value: string) => {
    setRenaming(false)
    const title = value.trim()
    if (title && title !== card.title) void onRename(title)
  }

  return (
    <ChartCard>
      {/* The same header as the chat card, without its shape badge: with four actions beside
          it the badge cut every title to a word and a half ("Income against..."). The shape is
          named under Details, next to the plan. */}
      <ChartCardHeader
        title={
          renaming ? (
            <Input
              aria-label="Chart title"
              autoFocus
              className="h-7 flex-1 text-sm"
              defaultValue={card.title}
              onBlur={(event) => rename(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') rename(event.currentTarget.value)
                if (event.key === 'Escape') setRenaming(false)
              }}
            />
          ) : (
            card.title
          )
        }
      >
        <span className="flex shrink-0 items-center gap-0.5 text-muted-foreground">
          <Button
            aria-label={`Move ${card.title} left`}
            disabled={first || busy}
            onClick={() => void onMove(card.position - 1)}
            size="icon-xs"
            variant="ghost"
          >
            <ChevronLeftIcon />
          </Button>
          <Button
            aria-label={`Move ${card.title} right`}
            disabled={last || busy}
            onClick={() => void onMove(card.position + 1)}
            size="icon-xs"
            variant="ghost"
          >
            <ChevronRightIcon />
          </Button>
          <Button
            aria-label={`Refresh ${card.title}`}
            disabled={busy}
            onClick={() => void onRefresh()}
            size="icon-xs"
            title="Run this chart's query again"
            variant="ghost"
          >
            <RefreshCwIcon className={busy ? 'animate-spin' : undefined} />
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button aria-label={`Actions for ${card.title}`} size="icon-xs" variant="ghost">
                <MoreHorizontalIcon />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-40">
              <DropdownMenuItem onSelect={() => setRenaming(true)}>
                <PencilIcon />
                Rename
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={() => setRemoving(true)} variant="destructive">
                <Trash2Icon />
                Remove
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </span>
      </ChartCardHeader>

      <CardBody chart={card} hasData={hasData} title={card.title} />

      <Footer
        actions={
          <span className="truncate text-muted-foreground text-xs">
            {busy
              ? 'Running the query...'
              : card.refreshed_at
                ? `Refreshed ${formatDateTime(card.refreshed_at)}`
                : 'Queried on this load'}
          </span>
        }
        output={card}
      />

      <ConfirmDialog
        action="Remove chart"
        description={`"${card.title}" is taken off the dashboard. The chat it came from keeps its own chart.`}
        onConfirm={async () => {
          await onRemove()
        }}
        onOpenChange={(open) => setRemoving(open)}
        open={removing}
        title="Remove this chart?"
      />
    </ChartCard>
  )
}
