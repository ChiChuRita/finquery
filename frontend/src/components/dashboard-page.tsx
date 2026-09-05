import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { ChartColumnIcon, SparklesIcon } from 'lucide-react'
import { useState, type ReactNode } from 'react'

import { DashboardCard, PreviewCard } from '@/components/dashboard-card'
import { PageBar } from '@/components/page'
import { Button } from '@/components/ui/button'
import { InputGroup, InputGroupAddon, InputGroupButton, InputGroupInput } from '@/components/ui/input-group'
import { Spinner } from '@/components/ui/spinner'
import {
  conversationsQuery,
  dashboardPinsQuery,
  dashboardQuery,
  deleteDashboardChart,
  keepDashboardChart,
  openReviewConversation,
  patchDashboardChart,
  previewDashboardChart,
  refreshDashboardChart,
  type ChartToolOutput,
  type DashboardTiles,
} from '@/lib/api'
import { formatEur } from '@/lib/format'
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

/** One headline figure: what it is, what it says, and what period it is about.
 *
 * The value is the point, so it carries the weight and keeps the font's own figures: tabular
 * digits are for columns that have to line up, and they make a large number look loose.
 */
function Tile({ label, value, note }: { label: string; value: string; note: ReactNode }) {
  return (
    <div className="rounded-xl border bg-card px-4 py-3">
      <p className="text-muted-foreground text-xs">{label}</p>
      <p className="mt-1 truncate font-semibold text-2xl tracking-tight" title={value}>
        {value}
      </p>
      <p className="mt-0.5 text-muted-foreground text-xs">{note}</p>
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
      <Tile label="Spent" note={month} value={euro(tiles.spent_eur)} />
      <Tile label="Income" note={month} value={euro(tiles.income_eur)} />
      <Tile label="Net" note={month} value={euro(tiles.net_eur)} />
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

/** The one line that makes a new card: a request in words, drawn by the chart sub-agent.
 *
 * It is the same `run_chart` a chat calls, so it takes about half a minute and shows the plan,
 * the query and any repair in the card's details. Nothing is stored until Keep.
 */
function AddChart({
  busy,
  onDraw,
}: {
  busy: boolean
  onDraw: (request: string) => void
}) {
  const [text, setText] = useState('')
  const submit = () => {
    const request = text.trim()
    if (!request || busy) return
    onDraw(request)
    setText('')
  }
  return (
    <InputGroup className="max-w-2xl">
      <InputGroupAddon>
        <ChartColumnIcon className="text-muted-foreground" />
      </InputGroupAddon>
      <InputGroupInput
        aria-label="Add a chart"
        disabled={busy}
        onChange={(event) => setText(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter') submit()
        }}
        placeholder="Add a chart: spending on groceries per month"
        value={text}
      />
      <InputGroupAddon align="inline-end">
        <InputGroupButton disabled={busy || !text.trim()} onClick={submit} variant="default">
          {busy ? <Spinner /> : <SparklesIcon />}
          {busy ? 'Drawing' : 'Draw it'}
        </InputGroupButton>
      </InputGroupAddon>
    </InputGroup>
  )
}

/** The dashboard: four figures, the cards this profile keeps, and a line that makes another.
 *
 * Every number on it was queried when the page loaded, never stored: a card holds a title, a
 * shape, its statement and its checked definition, and the statement is run again here through
 * the same guard the chat uses.
 */
export function DashboardPage() {
  const { profile } = useWorkspace()
  const queryClient = useQueryClient()
  const dashboard = useQuery(dashboardQuery(profile?.id))
  const [busyCard, setBusyCard] = useState<string>()
  const [request, setRequest] = useState<string>()
  const [preview, setPreview] = useState<ChartToolOutput>()
  const [keeping, setKeeping] = useState(false)
  const [problem, setProblem] = useState<string>()

  const profileId = profile?.id
  const reload = async () => {
    if (profileId) await queryClient.invalidateQueries(dashboardQuery(profileId))
  }

  const act = async (id: string, action: () => Promise<unknown>) => {
    setBusyCard(id)
    setProblem(undefined)
    try {
      await action()
      await reload()
    } catch (cause) {
      setProblem(cause instanceof Error ? cause.message : 'That did not work.')
    } finally {
      setBusyCard(undefined)
    }
  }

  const draw = async (text: string) => {
    if (!profileId) return
    setRequest(text)
    setPreview(undefined)
    setProblem(undefined)
    try {
      setPreview(await previewDashboardChart(profileId, text))
    } catch (cause) {
      setRequest(undefined)
      setProblem(cause instanceof Error ? cause.message : 'That chart could not be drawn.')
    }
  }

  const keep = async () => {
    if (!profileId || !preview) return
    setKeeping(true)
    try {
      await keepDashboardChart(profileId, preview)
      setPreview(undefined)
      setRequest(undefined)
      await reload()
    } catch (cause) {
      setProblem(cause instanceof Error ? cause.message : 'That chart could not be kept.')
    } finally {
      setKeeping(false)
    }
  }

  const drawing = request !== undefined && preview === undefined
  const charts = dashboard.data?.charts ?? []
  const hasData = dashboard.data?.has_data ?? false

  return (
    <div className="flex h-full min-h-0 flex-col">
      <PageBar title="Dashboard">
        <p className="truncate text-muted-foreground text-xs">
          Every figure here comes from a query this page just ran.
        </p>
        {dashboard.isFetching && !dashboard.isPending && (
          <Spinner className="size-3.5 text-muted-foreground" />
        )}
      </PageBar>

      <div className="min-h-0 flex-1 overflow-y-auto px-6 py-6">
        <div className="mx-auto flex w-full max-w-[1400px] flex-col gap-6">
          {dashboard.data && <Tiles tiles={dashboard.data.tiles} />}

          <div className="flex flex-col gap-2">
            <AddChart busy={drawing || keeping} onDraw={(text) => void draw(text)} />
            {problem && (
              <p className="text-destructive text-xs" role="alert">
                {problem}
              </p>
            )}
          </div>

          {dashboard.isPending || profileId === undefined ? (
            <p className="py-10 text-center text-muted-foreground text-sm">Loading the dashboard...</p>
          ) : (
            // Each card is as tall as its own content: a stretched card would end in a strip
            // of empty surface under its footer, and the cards are not a table.
            <div className="grid items-start gap-4 md:grid-cols-2 xl:grid-cols-3">
              {request !== undefined && (
                <PreviewCard
                  busy={keeping}
                  chart={preview}
                  onDiscard={() => {
                    setPreview(undefined)
                    setRequest(undefined)
                  }}
                  onKeep={() => void keep()}
                  request={request}
                />
              )}
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
                  onRefresh={() => act(card.id, () => refreshDashboardChart(profileId, card.id))}
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

          {!dashboard.isPending && charts.length === 0 && request === undefined && (
            <p className="py-10 text-center text-muted-foreground text-sm">
              This dashboard is empty. Ask for a chart above, or add one from a chat.
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
