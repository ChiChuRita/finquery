import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate, useSearch } from '@tanstack/react-router'
import { MoreHorizontalIcon, RotateCcwIcon } from 'lucide-react'
import { useState, type ReactNode } from 'react'

import { DashboardCard } from '@/components/dashboard-card'
import { DateRangePicker } from '@/components/date-range-picker'
import { PageBar } from '@/components/page'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Spinner } from '@/components/ui/spinner'
import {
  conversationsQuery,
  dashboardPinsQuery,
  dashboardQuery,
  deleteDashboardChart,
  openReviewConversation,
  patchDashboardChart,
  refreshDashboardChart,
  restoreDefaultCharts,
  type DashboardRange,
  type DashboardTiles,
  type DateRange,
  type TileMonth,
} from '@/lib/api'
import { formatEur, formatEurDelta, formatPercentDelta } from '@/lib/format'
import { useWorkspace } from '@/lib/workspace'

/** "2025-12" as a month a person reads. The UI is English; the money stays German. */
const monthName = (month: string | null) => {
  if (!month) return 'No bookings yet'
  const [year, index] = month.split('-')
  const date = new Date(Number(year), Number(index) - 1, 1)
  return Number.isNaN(date.getTime())
    ? month
    : date.toLocaleDateString('en-GB', { month: 'long', year: 'numeric' })
}

const euro = (amount: number) => formatEur(Math.round(amount * 100))

/** One comparison under a tile: the difference, and whether that direction is good news. */
interface Delta {
  label: string
  /** The difference in euros, signed, and the same difference as a share of what it is against. */
  amount: number
  share: number | null
  /** True when this direction is the one a household wants. Null when there is no direction. */
  good: boolean | null
  /** The month or the months the figure was compared with, for the line's own tooltip. */
  against: string
}

/** Which figure of a month a tile is about, and which way is up for it.
 *
 * Spending falling is good news, income and net rising are. That is the only thing the colour
 * of a delta says, so it is decided here once rather than at three call sites.
 */
type Direction = 'down-is-good' | 'up-is-good'

/** The two comparisons of one tile, computed from the months the tiles' statement returned.
 *
 * Both are arithmetic on those rows and nothing else: the newest month against the one before
 * it, and against the mean of the earlier ones. Every figure came out of the guarded query, and
 * subtracting two of them is what `fold_rows` does to rows on the server (ADR 0004).
 */
function deltasOf(months: TileMonth[], read: (month: TileMonth) => number, way: Direction): Delta[] {
  if (months.length < 2) return []
  const value = read(months[months.length - 1])
  const earlier = months.slice(0, -1)
  const previous = read(earlier[earlier.length - 1])
  const average = earlier.reduce((sum, month) => sum + read(month), 0) / earlier.length
  const compare = (label: string, against: number, describes: string): Delta => {
    const amount = value - against
    const rising = Math.abs(amount) < 0.005 ? null : amount > 0
    return {
      label,
      amount,
      share: against === 0 ? null : amount / Math.abs(against),
      good: rising === null ? null : way === 'up-is-good' ? rising : !rising,
      against: describes,
    }
  }
  return [
    compare('vs last month', previous, `${monthName(earlier[earlier.length - 1].month)}: ${euro(previous)}`),
    compare(
      `vs ${earlier.length}-month average`,
      average,
      `${monthName(earlier[0].month)} to ${monthName(earlier[earlier.length - 1].month)}: ${euro(average)}`,
    ),
  ]
}

/** One comparison as a line: the signed euros, the share, and what it is against.
 *
 * The sign carries the direction on its own, so the colour is a second reading of it and never
 * the only one. The line wraps rather than truncating: "vs 6-month average" cut to "vs 6-month
 * ave..." is a comparison the reader has to hover to identify.
 */
function DeltaLine({ delta }: { delta: Delta }) {
  return (
    <p className="text-[11px] leading-tight" title={`${delta.label}, ${delta.against}`}>
      <span
        className={
          delta.good === null
            ? 'whitespace-nowrap text-muted-foreground'
            : delta.good
              ? 'whitespace-nowrap text-primary'
              : 'whitespace-nowrap text-destructive'
        }
      >
        {formatEurDelta(Math.round(delta.amount * 100))}
        {delta.share !== null && ` (${formatPercentDelta(delta.share)})`}
      </span>{' '}
      {/* Neither half breaks inside itself: a narrow tile puts the label on its own line,
          rather than splitting "6-month" at its hyphen. */}
      <span className="whitespace-nowrap text-muted-foreground">{delta.label}</span>
    </p>
  )
}

/** One headline figure: what it is, what it says, what period it is about, and its comparisons.
 *
 * The value is the point, so it carries the weight and keeps the font's own figures: tabular
 * digits are for columns that have to line up, and they make a large number look loose.
 */
function Tile({
  label,
  value,
  note,
  deltas = [],
}: {
  label: string
  value: string
  note: ReactNode
  deltas?: Delta[]
}) {
  return (
    <div className="rounded-xl border bg-card px-4 py-3">
      <p className="text-muted-foreground text-xs">{label}</p>
      <p className="mt-1 truncate font-semibold text-2xl tracking-tight" title={value}>
        {value}
      </p>
      <p className="mt-0.5 text-muted-foreground text-xs">{note}</p>
      {deltas.length > 0 && (
        <div className="mt-2 flex flex-col gap-1">
          {deltas.map((delta) => (
            <DeltaLine delta={delta} key={delta.label} />
          ))}
        </div>
      )}
    </div>
  )
}

/** The four figures the page opens with, every one of them from a query run just now. */
function Tiles({ tiles }: { tiles: DashboardTiles }) {
  const { profile } = useWorkspace()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [opening, setOpening] = useState(false)
  const month = monthName(tiles.month)

  // The bookings without a category are asked about in the chat, on the Question card the
  // import already has waiting. It is the same door the Imports page opens.
  const review = async () => {
    if (!profile || !tiles.review_import_id || opening) return
    setOpening(true)
    try {
      const conversation = await openReviewConversation(tiles.review_import_id, profile.id)
      void queryClient.invalidateQueries(conversationsQuery(profile.id))
      await navigate({ to: '/c/$conversationId', params: { conversationId: conversation.conversation_id } })
    } finally {
      setOpening(false)
    }
  }

  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
      <Tile
        deltas={deltasOf(tiles.months, (row) => row.spent_eur, 'down-is-good')}
        label="Spent"
        note={month}
        value={euro(tiles.spent_eur)}
      />
      <Tile
        deltas={deltasOf(tiles.months, (row) => row.income_eur, 'up-is-good')}
        label="Income"
        note={month}
        value={euro(tiles.income_eur)}
      />
      <Tile
        deltas={deltasOf(tiles.months, (row) => row.net_eur, 'up-is-good')}
        label="Net"
        note={month}
        value={euro(tiles.net_eur)}
      />
      <Tile
        label="Needs review"
        note={
          tiles.review_import_id ? (
            <Button
              className="h-auto p-0 text-xs"
              disabled={opening}
              onClick={() => void review()}
              variant="link"
            >
              {opening ? 'Opening the chat...' : 'Answer them in a chat'}
            </Button>
          ) : (
            'Bookings without a category'
          )
        }
        value={String(tiles.needs_review)}
      />
    </div>
  )
}

/** A day `months` before this one, in ISO. Enough date arithmetic for four preset chips. */
function monthsBefore(day: string, months: number): string {
  const [year, month, date] = day.split('-').map(Number)
  return new Date(Date.UTC(year, month - 1 - months, date)).toISOString().slice(0, 10)
}

/** The presets, counted back from the newest booking rather than from today, the way the tiles
 *  and the twelve-month defaults are. A profile with no bookings has nothing to count from. */
function presetsFor(lastDay: string | null): { label: string; range: DateRange }[] {
  const all = { label: 'All', range: { from: '', to: '' } }
  if (!lastDay) return [all]
  return [
    { label: 'This month', range: { from: `${lastDay.slice(0, 7)}-01`, to: lastDay } },
    { label: 'Last 3 months', range: { from: monthsBefore(lastDay, 3), to: lastDay } },
    { label: 'This year', range: { from: `${lastDay.slice(0, 4)}-01-01`, to: lastDay } },
    all,
  ]
}

const sameRange = (one: DateRange, other: DateRange) => one.from === other.from && one.to === other.to

/** The days the whole page is about: four chips and two date fields.
 *
 * It narrows the tiles and every card in one request, and nothing about it is stored: it lives
 * in the URL, so a reload, the back button and a shared link all show the same days.
 */
function RangeBar({
  range,
  applied,
  onChange,
}: {
  range: DateRange
  applied?: DashboardRange
  onChange: (next: DateRange) => void
}) {
  const presets = presetsFor(applied?.last_day ?? null)
  const whole = applied?.first_day
    ? `All · ${applied.first_day.split('-').reverse().join('.')} to ${applied.last_day?.split('-').reverse().join('.')}`
    : 'All'
  return (
    <div className="flex flex-wrap items-center gap-2">
      {presets.map((preset) => (
        <Button
          key={preset.label}
          onClick={() => onChange(preset.range)}
          size="sm"
          variant={sameRange(range, preset.range) ? 'secondary' : 'ghost'}
        >
          {preset.label === 'All' ? whole : preset.label}
        </Button>
      ))}
      <span className="ml-auto">
        <DateRangePicker from={range.from} onChange={onChange} to={range.to} />
      </span>
    </div>
  )
}

/** The dashboard: four figures, the cards this profile keeps, and the days they are about.
 *
 * Every number on it was queried when the page loaded, never stored: a card holds a title, a
 * shape, its statement and its checked definition, and the statement is run again here through
 * the same guard the chat uses. Charts are asked for in a chat, so this page has no composer:
 * the ones the assistant kept, and the ones added from a transcript, are what is here.
 */
export function DashboardPage() {
  const { profile } = useWorkspace()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const search = useSearch({ from: '/dashboard' })
  const range: DateRange = { from: search.from ?? '', to: search.to ?? '' }
  const dashboard = useQuery(dashboardQuery(profile?.id, range))
  const [busyCard, setBusyCard] = useState<string>()
  const [problem, setProblem] = useState<string>()
  const [notice, setNotice] = useState<string>()
  const [restoring, setRestoring] = useState(false)

  const profileId = profile?.id
  const reload = async () => {
    if (profileId) await queryClient.invalidateQueries(dashboardQuery(profileId, range))
  }

  const act = async (id: string, action: () => Promise<unknown>) => {
    setBusyCard(id)
    setProblem(undefined)
    setNotice(undefined)
    try {
      await action()
      await reload()
    } catch (cause) {
      setProblem(cause instanceof Error ? cause.message : 'That did not work.')
    } finally {
      setBusyCard(undefined)
    }
  }

  // The shipped cards a profile is missing, and only those: a default that was renamed, moved
  // or edited counts as present, and nothing the user made is touched.
  const restore = async () => {
    if (!profileId || restoring) return
    setRestoring(true)
    setProblem(undefined)
    setNotice(undefined)
    try {
      const { added } = await restoreDefaultCharts(profileId, range)
      await reload()
      setNotice(
        added.length === 0
          ? 'Every default card is already on this dashboard.'
          : added.length === 1
            ? 'One default card was added at the end.'
            : `${added.length} default cards were added at the end.`,
      )
    } catch (cause) {
      setProblem(cause instanceof Error ? cause.message : 'That did not work.')
    } finally {
      setRestoring(false)
    }
  }

  // An empty end is left out of the URL rather than written as an empty parameter, so no range
  // at all is the plain `/dashboard` a shared link should be.
  const setRange = (next: DateRange) =>
    void navigate({
      to: '/dashboard',
      search: { from: next.from || undefined, to: next.to || undefined },
      replace: true,
    })

  const charts = dashboard.data?.charts ?? []
  const hasData = dashboard.data?.has_data ?? false

  return (
    <div className="flex h-full min-h-0 flex-col">
      <PageBar title="Dashboard">
        <p className="truncate text-muted-foreground text-xs">
          Every figure here comes from a query this page just ran. Ask for a chart in a chat;
          the ones worth keeping land here.
        </p>
        {dashboard.isFetching && !dashboard.isPending && (
          <Spinner className="size-3.5 text-muted-foreground" />
        )}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              aria-label="Dashboard actions"
              className="ml-auto shrink-0"
              disabled={profileId === undefined}
              size="icon-xs"
              variant="ghost"
            >
              <MoreHorizontalIcon />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56">
            <DropdownMenuItem disabled={restoring} onSelect={() => void restore()}>
              <RotateCcwIcon />
              Restore default cards
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </PageBar>

      <div className="min-h-0 flex-1 overflow-y-auto px-6 py-6">
        <div className="mx-auto flex w-full max-w-[1400px] flex-col gap-6">
          <RangeBar applied={dashboard.data?.range} onChange={setRange} range={range} />

          {dashboard.data && <Tiles tiles={dashboard.data.tiles} />}

          {problem && (
            <p className="text-destructive text-xs" role="alert">
              {problem}
            </p>
          )}

          {notice && (
            <p className="text-muted-foreground text-xs" role="status">
              {notice}
            </p>
          )}

          {dashboard.isPending || profileId === undefined ? (
            <p className="py-10 text-center text-muted-foreground text-sm">Loading the dashboard...</p>
          ) : (
            // Each card is as tall as its own content: a stretched card would end in a strip
            // of empty surface under its footer, and the cards are not a table.
            <div className="grid items-start gap-4 md:grid-cols-2 xl:grid-cols-3">
              {charts.map((card, index) => (
                <DashboardCard
                  busy={busyCard === card.id}
                  card={card}
                  first={index === 0}
                  hasData={hasData}
                  key={card.id}
                  last={index === charts.length - 1}
                  onMove={(position) =>
                    act(card.id, () => patchDashboardChart(profileId, card.id, { position }))
                  }
                  onRefresh={() => act(card.id, () => refreshDashboardChart(profileId, card.id, range))}
                  onRemove={() =>
                    act(card.id, async () => {
                      await deleteDashboardChart(profileId, card.id)
                      await queryClient.invalidateQueries(dashboardPinsQuery(profileId))
                    })
                  }
                  onRename={(title) =>
                    act(card.id, () => patchDashboardChart(profileId, card.id, { title }))
                  }
                />
              ))}
            </div>
          )}

          {!dashboard.isPending && charts.length === 0 && (
            <div className="flex flex-col items-center gap-3 py-10 text-center">
              <p className="text-muted-foreground text-sm">
                This dashboard is empty. Ask for a chart in a chat; the ones worth keeping land here.
              </p>
              <Button asChild size="sm" variant="outline">
                <Link to="/">Ask for a chart</Link>
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
