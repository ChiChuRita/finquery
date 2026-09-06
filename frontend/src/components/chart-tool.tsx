import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ChartColumnIcon,
  CheckIcon,
  ChevronDownIcon,
  CircleAlertIcon,
  ClipboardListIcon,
  Code2Icon,
  DatabaseIcon,
  LayoutDashboardIcon,
  RefreshCwIcon,
  ShieldCheckIcon,
  WrenchIcon,
  type LucideIcon,
} from 'lucide-react'
import { useEffect, useRef, useState, type ReactNode } from 'react'

import {
  ChainOfThought,
  ChainOfThoughtContent,
  ChainOfThoughtStep,
} from '@/components/ai-elements/chain-of-thought'
import { Shimmer } from '@/components/ai-elements/shimmer'
import { FeedbackError, PairGrid, PairSide, Thumbs, useFeedback } from '@/components/feedback'
import { RowsTable, Section, SqlSection, rowLabel } from '@/components/query-result'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import {
  chartAlternative,
  chartRenderFailure,
  dashboardPinsQuery,
  deleteDashboardChart,
  pinChartToDashboard,
  type ChartDetails,
  type ChartToolOutput,
  type ChartToolPart,
  type PreferenceRating,
} from '@/lib/api'
import { cn } from '@/lib/utils'
import { useWorkspace } from '@/lib/workspace'
import {
  CARD_SOURCE,
  CHART_HEIGHT,
  FRAME_URL,
  isFrameMessage,
  type ChartFrameTheme,
  type ChartLanguage,
  type ChartRow,
} from '@/lib/chart-frame'

export const SHAPE_LABELS: Record<string, string> = {
  line: 'Line',
  area: 'Area',
  bar: 'Bars',
  bar_horizontal: 'Bars',
  bar_grouped: 'Grouped bars',
  bar_stacked: 'Stacked bars',
  doughnut: 'Doughnut',
  sankey: 'Sankey',
}

/** Where a reason stops being a sentence and starts being quoted code. */
const QUOTED_CODE = /\n|--|\/\*|```|\bWITH\b|\bSELECT\b|\bAS \(/
const HEADLINE = 160

/** The one line a failed card shows.
 *
 * A failure reason quotes whatever refused the chart, and that can be the sub-agent's own
 * statement with its scratch notes in it ("-- This is wrong, I want top spenders ... -- Let's
 * try aga"). A comment the model wrote to itself is not an error message, so the line stops
 * where the quoted code starts; the whole reason stays under the details toggle, where the plan
 * and the SQL already are.
 */
export function failureLine(error: string): string {
  const parts = error.split(QUOTED_CODE)
  let said = parts[0].trim().replace(/[\s,;:]+$/, '')
  // Cutting the code off can leave half a clause behind (", top_categories"), so a line that
  // was cut ends on the last sentence that finished.
  if (parts.length > 1 && !said.endsWith('.')) {
    const stop = said.lastIndexOf('.')
    if (stop > 0) said = said.slice(0, stop + 1)
  }
  if (!said) return 'The chart could not be drawn.'
  if (said.length <= HEADLINE) return said
  const cut = said.lastIndexOf(' ', HEADLINE)
  return `${said.slice(0, cut > 0 ? cut : HEADLINE).trimEnd()}...`
}

/** The app's own colours, resolved, because the sandboxed frame cannot read our stylesheet. */
function readTheme(): ChartFrameTheme {
  const style = getComputedStyle(document.documentElement)
  const read = (name: string, fallback: string) => style.getPropertyValue(name).trim() || fallback
  const border = read('--border', 'rgb(0 0 0 / 0.12)')
  return {
    color: read('--foreground', '#171717'),
    muted: read('--muted-foreground', '#737373'),
    grid: border,
    surface: read('--card', '#ffffff'),
    border,
    palette: [1, 2, 3, 4, 5, 6].map((index) => read(`--chart-${index}`, '#0f766e')),
  }
}

/** One chart, hosted in a sandboxed frame that owns React and TanStack Charts.
 *
 * `onError` is what makes a failure more than a red box: the card reports it to the server,
 * which records it on the turn and draws the request once more.
 */
export function ChartFrame({
  title,
  language,
  code,
  rows,
  onError,
}: {
  title: string
  language: ChartLanguage
  code: string
  rows: ChartRow[]
  onError?: (message: string) => void
}) {
  const frame = useRef<HTMLIFrameElement>(null)
  // Every reason to (re)send the render message, counted rather than flagged: a frame that
  // loaded a second time needs it again, and a flag that is already true changes nothing. A
  // card the dashboard moves is exactly that case, because a browser reloads an iframe whose
  // element is re-inserted, and the reloaded document waits for a message that never comes.
  const [posts, setPosts] = useState(0)
  const [live, setLive] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // The theme toggle flips a class on <html>; watching it is independent of effect ordering.
  const [themeChanges, setThemeChanges] = useState(0)

  // The message listener is installed once, so the callback reaches it through a ref rather
  // than by re-subscribing on every render.
  const report = useRef(onError)
  useEffect(() => {
    report.current = onError
  })

  useEffect(() => {
    const observer = new MutationObserver(() => setThemeChanges((count) => count + 1))
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    const onMessage = (event: MessageEvent) => {
      if (event.source !== frame.current?.contentWindow || !isFrameMessage(event.data)) return
      if (event.data.kind === 'hello') setPosts((count) => count + 1)
      if (event.data.kind === 'ready') {
        setError(null)
        setLive(true)
      }
      if (event.data.kind === 'error') {
        setError(event.data.message)
        setLive(false)
        report.current?.(event.data.message)
      }
    }
    window.addEventListener('message', onMessage)
    return () => window.removeEventListener('message', onMessage)
  }, [])

  useEffect(() => {
    if (posts === 0) return
    frame.current?.contentWindow?.postMessage(
      { source: CARD_SOURCE, kind: 'render', title, language, code, rows, theme: readTheme() },
      '*',
    )
  }, [posts, title, language, code, rows, themeChanges])

  return (
    <div className="relative" style={{ height: CHART_HEIGHT }}>
      <iframe
        // Invisible until the runtime says it painted, then a short fade: the frame's own
        // surface is the card's colour, so what appears is the drawing and not a white flash.
        className={cn('h-full w-full border-0 transition-opacity duration-300', live ? 'opacity-100' : 'opacity-0')}
        // The frame's "hello" can arrive before React has run this component's effects, so the
        // load event is the reliable trigger and the message is only a second chance.
        onLoad={() => {
          // A reloaded frame is blank until it is told what to draw again, so it says
          // "Drawing..." rather than showing its own white surface.
          setLive(false)
          setPosts((count) => count + 1)
        }}
        ref={frame}
        sandbox="allow-scripts"
        src={FRAME_URL}
        title={title}
      />
      {!live && !error && (
        <div className="absolute inset-0 flex items-center justify-center">
          <Shimmer className="text-sm">Drawing...</Shimmer>
        </div>
      )}
      {error && (
        <div className="absolute inset-0 flex items-center justify-center px-4">
          <FailedBody reason={`This chart could not be drawn: ${error}`} />
        </div>
      )}
    </div>
  )
}

/** The frame's place while a chart is still being made, at the frame's own height.
 *
 * The transcript must not jump when the drawing arrives, so the running card is already as tall
 * as the card it becomes. The chat and the dashboard's Add line show the same thing. */
export function RunningBody() {
  return (
    <div className="flex items-center justify-center px-4" style={{ height: CHART_HEIGHT }}>
      <Shimmer className="text-muted-foreground text-sm">Planning, querying, drawing...</Shimmer>
    </div>
  )
}

/** Why there is no drawing, in one quiet block: the reason, and where the rest is.
 *
 * One component for the chat card, the dashboard card and the frame's own refusal, so a failure
 * looks the same wherever it happens. `note` carries the one thing a state has to add. */
export function FailedBody({ reason, hint, note }: { reason: string; hint?: string; note?: ReactNode }) {
  return (
    <Alert className="border-destructive/25 bg-destructive/5 text-destructive">
      <CircleAlertIcon />
      <AlertTitle className="text-sm leading-snug">{reason}</AlertTitle>
      {(hint || note) && (
        <AlertDescription className="text-muted-foreground text-xs">
          {hint}
          {note}
        </AlertDescription>
      )}
    </Alert>
  )
}

type ChainStatus = 'complete' | 'active' | 'pending'

interface ChainStep {
  icon: LucideIcon
  label: string
  description?: string
  status: ChainStatus
}

const repairsLine = (count: number) =>
  count === 0 ? 'Self-check passed' : `Self-check passed after ${count === 1 ? 'one repair' : `${count} repairs`}`

/** The steps a chart still being made has reached, read off the sub-agent's narration.
 *
 * `chart/runner.py` narrates "Chart plan: ...", "Data: N rows over ...", "Repair k of 2: ..." and
 * "Self-check passed" into the turn's thinking as it goes, so the rail can move with it rather
 * than sit on "Planning" for the whole half minute. Nothing is guessed: a step is complete when
 * its own line has arrived. */
function runningSteps(narration: string): ChainStep[] {
  const planned = narration.includes('Chart plan:')
  const queried = /\bData: \d+ rows?\b/.test(narration)
  const repairs = narration.match(/^Repair \d+ of \d+: .*$/gm) ?? []
  const checked = /Self-check passed/.test(narration)
  const wrote = checked || repairs.length > 0
  const at = (done: boolean, active: boolean): ChainStatus => (done ? 'complete' : active ? 'active' : 'pending')
  return [
    { icon: ClipboardListIcon, label: planned ? 'Planned the chart' : 'Planning the chart', status: at(planned, true) },
    { icon: DatabaseIcon, label: queried ? 'Queried the rows' : 'Querying the rows', status: at(queried, planned) },
    {
      icon: Code2Icon,
      label: wrote ? 'Wrote the chart definition' : 'Writing the chart definition',
      status: at(wrote, queried),
    },
    ...repairs.map((note): ChainStep => ({ icon: WrenchIcon, label: note, status: 'complete' })),
    { icon: ShieldCheckIcon, label: checked ? repairsLine(repairs.length) : 'Checking it', status: at(checked, wrote) },
  ]
}

/** The four things the chart sub-agent does, plus one step per repair round it needed.
 *
 * The words are the ones it narrates while it works (`chart/runner.py`): the plan, the data
 * line, each repair and the self-check verdict. A chart still being made has no output to read
 * yet, so its rail shows the first step active and the rest pending; once the tool has answered,
 * every step it reached is complete and the ones it never got to stay pending.
 */
function chartSteps(output?: ChartDetails, narration = ''): ChainStep[] {
  if (!output) return runningSteps(narration)
  const reached = (done: boolean): ChainStatus => (done ? 'complete' : 'pending')
  const drawn = Boolean(output.code) && !output.error
  // One note per repair round, and, for a chart shown with a rule it could not satisfy, the
  // reason as one more. That last one is the verdict of the check, not a round of its own.
  const rounds = output.notes.filter((note) => note.startsWith('Repair ') || note.startsWith('Gave up'))
  const unmet = output.notes.find((note) => !rounds.includes(note))
  return [
    {
      icon: ClipboardListIcon,
      label: 'Planned the chart',
      description: output.plan || undefined,
      status: reached(Boolean(output.plan)),
    },
    {
      icon: DatabaseIcon,
      label: output.sql ? `Queried the rows · ${rowLabel(output.row_count)}` : 'The query returned nothing to draw',
      description: output.sql ? output.columns.join(', ') : undefined,
      status: reached(Boolean(output.sql)),
    },
    {
      icon: Code2Icon,
      label: 'Wrote the chart definition',
      description: output.code ? (SHAPE_LABELS[output.shape] ?? output.shape) : undefined,
      status: reached(Boolean(output.code)),
    },
    ...rounds.map((note): ChainStep => ({ icon: WrenchIcon, label: note, status: 'complete' })),
    {
      icon: ShieldCheckIcon,
      label: unmet ?? (drawn ? repairsLine(rounds.length) : 'The chart was not drawn'),
      description: drawn || unmet ? undefined : failureLine(output.error ?? ''),
      status: reached(drawn || Boolean(unmet)),
    },
  ]
}

/** How this chart was made, on the icon rail: the plan, the query, the code and the check.
 *
 * It lives inside the details and nowhere else. The card, the query step and the changeset are
 * the audit trail of the answer and must stay open on the page; this is the sub-agent's own
 * work, which is worth reading once and then folding away.
 */
function ChartChain({ output, narration }: { output?: ChartDetails; narration?: string }) {
  return (
    <ChainOfThought open>
      <ChainOfThoughtContent>
        {/* Keyed by position: two repair rounds can leave the same note behind. */}
        {chartSteps(output, narration).map((step, index) => (
          <ChainOfThoughtStep
            description={step.description}
            icon={step.icon}
            key={index}
            label={step.label}
            status={step.status}
          />
        ))}
      </ChainOfThoughtContent>
    </ChainOfThought>
  )
}

/** The audit trail under every chart: what was asked, how it was made, what ran and the rows.
 *
 * A chart still being made opens this by itself, because the chain of thought inside it is the
 * only thing there is to watch while nothing is drawn yet. The finished card starts folded, the
 * way it always did.
 */
export function Footer({
  output,
  running = false,
  narration,
  actions,
}: {
  output?: ChartDetails
  running?: boolean
  /** The turn's thinking so far, while the chart is being made: the rail advances on it. */
  narration?: string
  actions?: ReactNode
}) {
  const [open, setOpen] = useState(running)
  return (
    <Collapsible onOpenChange={setOpen} open={open}>
      <div className="flex items-center justify-between gap-2 border-t px-2 py-1.5">
        <CollapsibleTrigger asChild>
          <Button className="gap-1.5 text-muted-foreground" size="sm" variant="ghost">
            <ChevronDownIcon className={open ? 'rotate-180 transition-transform' : 'transition-transform'} />
            {output?.sql ? `SQL and ${rowLabel(output.row_count)}` : 'Details'}
          </Button>
        </CollapsibleTrigger>
        {actions}
      </div>
      <CollapsibleContent className="space-y-4 border-t px-4 pt-3 pb-4">
        {/* While the chart is being made the card's own heading is the request, so it is not
            repeated here. */}
        {output && (
          <Section label="Request">
            <p className="text-sm">{output.request}</p>
          </Section>
        )}
        <Section label="How this chart was made">
          <ChartChain narration={narration} output={output} />
        </Section>
        {output?.error && (
          // The card says the failure in one line; what was quoted into it, code and all, is here.
          <Section label="Why it failed">
            <p className="whitespace-pre-wrap break-words rounded-md bg-muted px-3 py-2 font-mono text-muted-foreground text-xs">
              {output.error}
            </p>
          </Section>
        )}
        {output?.sql && <SqlSection sql={output.sql} />}
        {output && output.row_count > 0 && (
          <Section label={`Rows · ${rowLabel(output.row_count)}`}>
            <RowsTable columns={output.columns} rows={output.rows} />
          </Section>
        )}
      </CollapsibleContent>
    </Collapsible>
  )
}

/** The card's shell. rounded-lg is the transcript's radius; a page passes its own (ticket 45). */
export function ChartCard({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn('w-full overflow-hidden rounded-lg border bg-card', className)} data-slot="chart-card">
      {children}
    </div>
  )
}

/** The top of a chart card: what it shows, what it is, and, on the dashboard, what can be done
 *  to it. `title` takes a node so a card being renamed can put its input where its title was. */
export function ChartCardHeader({
  title,
  shape,
  children,
}: {
  title: ReactNode
  shape?: string
  children?: ReactNode
}) {
  return (
    <div className="flex items-start justify-between gap-3 px-4 pt-3 pb-2">
      {typeof title === 'string' ? (
        <h3 className="line-clamp-2 min-w-0 flex-1 font-medium text-sm leading-snug" title={title}>
          {title}
        </h3>
      ) : (
        title
      )}
      {shape && (
        <Badge className="shrink-0 gap-1 font-normal text-muted-foreground" variant="outline">
          <ChartColumnIcon className="size-3" />
          {SHAPE_LABELS[shape] ?? shape}
        </Badge>
      )}
      {children}
    </div>
  )
}

/** A drawn chart, its rating, and the second chart a Regenerate produced.
 *
 * The pair lives in the card, not in the transcript: the regenerate is no chat turn, so the
 * second chart is here until the user picks one or leaves the page. What the pick leaves behind
 * is the preference record, and after a reload the card shows the chart the turn stored with a
 * line saying a pair was collected.
 */
function ChartResult({
  output,
  toolCallId,
  turnId,
  rating,
}: {
  output: ChartToolOutput
  toolCallId: string
  turnId?: string
  rating?: PreferenceRating
}) {
  const { profile } = useWorkspace()
  const feedback = useFeedback(turnId, toolCallId, rating)
  const [second, setSecond] = useState<ChartToolOutput>()
  const [drawing, setDrawing] = useState(false)
  const [problem, setProblem] = useState<string>()
  const [again, setAgain] = useState(false)
  const [picked, setPicked] = useState<'original' | 'candidate'>()
  const [redrawn, setRedrawn] = useState<ChartToolOutput>()
  const [retrying, setRetrying] = useState(false)
  // A side of a pair the browser could not draw. Picking one of two charts means saying which
  // is better, which nobody can do about an error message (review of 2026-09-04).
  const [broken, setBroken] = useState<Record<'original' | 'candidate', boolean>>({
    original: false,
    candidate: false,
  })
  // One report per chart: the server retries once, and a remount must not ask again.
  const reported = useRef(false)
  // Which charts of this profile are on the dashboard. One cheap request per profile, shared
  // by every card in the transcript, so a reload still knows this one is kept.
  const queryClient = useQueryClient()
  const { data: pins } = useQuery(dashboardPinsQuery(profile?.id))
  const [pinning, setPinning] = useState(false)
  // The agent can keep a chart itself, from inside the tool (ticket 44). That card exists
  // before the pins query is refetched, so the tool's own answer is read first and the pins
  // are what a reload reads.
  const [keptId, setKeptId] = useState<string | undefined>(
    output.kept ? (output.dashboard_chart_id ?? undefined) : undefined,
  )
  const cardId = pins?.charts.find((entry) => entry.call_id === toolCallId)?.chart_id ?? keptId
  const pinned = cardId !== undefined

  // What this card shows: the chart of the turn, or the one a retry drew in its place.
  const chart = redrawn ?? output
  const title = chart.title || chart.request
  // A chart written for an English question says so, and the frame writes its months in it.
  const language: ChartLanguage = chart.language ?? 'de'
  // The definition to draw, or null when this chart failed and the card shows the reason.
  const code = chart.error ? null : chart.code

  const renderFailed = async (message: string) => {
    if (!profile || !turnId || reported.current) return
    reported.current = true
    setRetrying(true)
    try {
      const outcome = await chartRenderFailure(profile.id, turnId, toolCallId, message)
      // Whichever way it went, the card shows what the server recorded: the chart the retry
      // drew, or the failure with its reason and the rows behind it.
      setRedrawn(outcome.chart)
    } catch {
      // The card already shows the frame's own message; a failed report changes nothing.
    } finally {
      setRetrying(false)
    }
  }

  const addToDashboard = async () => {
    if (!profile || !turnId || pinning) return
    setPinning(true)
    setProblem(undefined)
    try {
      const card = await pinChartToDashboard(profile.id, turnId, toolCallId)
      setKeptId(card.id)
      await queryClient.invalidateQueries(dashboardPinsQuery(profile.id))
      void queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    } catch (cause) {
      setProblem(cause instanceof Error ? cause.message : 'That chart could not be added.')
    } finally {
      setPinning(false)
    }
  }

  // The other half of the agent keeping a chart by itself: one click undoes a wrong call, and
  // the chart stays in this transcript either way.
  const removeFromDashboard = async () => {
    if (!profile || !cardId || pinning) return
    setPinning(true)
    setProblem(undefined)
    try {
      await deleteDashboardChart(profile.id, cardId)
      setKeptId(undefined)
      await queryClient.invalidateQueries(dashboardPinsQuery(profile.id))
      void queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    } catch (cause) {
      setProblem(cause instanceof Error ? cause.message : 'That chart could not be removed.')
    } finally {
      setPinning(false)
    }
  }

  const regenerate = async () => {
    if (!profile || !turnId || drawing) return
    setDrawing(true)
    setProblem(undefined)
    setAgain(false)
    try {
      const alternative = await chartAlternative(profile.id, turnId, toolCallId)
      if (alternative.error || !alternative.code) {
        setProblem(alternative.error ?? 'The second chart could not be drawn.')
        return
      }
      // The sub-agent can write exactly the same definition again. There is nothing to pick
      // between two identical charts, and such a pair would teach a training run nothing.
      if (alternative.code === code) {
        setAgain(true)
        return
      }
      setSecond(alternative)
      setPicked(undefined)
    } catch (cause) {
      setProblem(cause instanceof Error ? cause.message : 'The second chart could not be drawn.')
    } finally {
      setDrawing(false)
    }
  }

  const pick = async (which: 'original' | 'candidate') => {
    if (!second?.code) return
    await feedback.pick(which, { code: second.code, shape: second.shape, title: second.title })
    setPicked(which)
  }

  return (
    <ChartCard>
      <ChartCardHeader shape={chart.shape} title={title} />
      {retrying && (
        <div className="px-4 pb-2">
          <Shimmer className="text-muted-foreground text-sm">
            That chart did not draw. Trying once more...
          </Shimmer>
        </div>
      )}
      {code && second?.code ? (
        <div className="px-3 pb-3">
          <PairGrid>
            <PairSide
              disabled={feedback.busy}
              label="The first chart"
              note={SHAPE_LABELS[chart.shape] ?? chart.shape}
              onPick={() => void pick('original')}
              picked={picked === 'original'}
              unavailable={broken.original ? 'This one did not draw.' : undefined}
            >
              <ChartFrame
                code={code}
                language={language}
                onError={() => setBroken((sides) => ({ ...sides, original: true }))}
                rows={chart.rows}
                title={title}
              />
            </PairSide>
            <PairSide
              disabled={feedback.busy}
              label="Drawn again"
              note={SHAPE_LABELS[second.shape] ?? second.shape}
              onPick={() => void pick('candidate')}
              picked={picked === 'candidate'}
              unavailable={broken.candidate ? 'This one did not draw.' : undefined}
            >
              <ChartFrame
                code={second.code}
                language={second.language ?? language}
                onError={() => setBroken((sides) => ({ ...sides, candidate: true }))}
                rows={second.rows}
                title={second.title || title}
              />
            </PairSide>
          </PairGrid>
          <p className="pt-2 text-muted-foreground text-xs">
            {picked
              ? 'Stored as a preference pair. Both charts drew the rows of the same query.'
              : 'Both charts drew the rows of the same query. Pick the better one.'}
          </p>
        </div>
      ) : code ? (
        <ChartFrame
          code={code}
          language={language}
          onError={(message) => void renderFailed(message)}
          rows={chart.rows}
          title={title}
        />
      ) : (
        <div className="px-4 pb-3">
          <FailedBody
            hint="Nothing was drawn. The whole reason, the plan and the query it tried are under Details."
            // A chart that passed the check and then failed in the browser was `rendered: true`
            // when the model read the tool result, so the answer under this card describes a
            // picture that is not here. Re-running the turn is a bigger change than saying so.
            note={
              chart.render_error && (
                <span className="mt-1 block">
                  This one passed the check and failed in the browser, after the answer below was
                  written: read the rows rather than what it says about the picture.
                </span>
              )
            }
            reason={failureLine(chart.error ?? '')}
          />
        </div>
      )}
      <Footer
        actions={
          <span className="flex items-center gap-1">
            <FeedbackError message={feedback.error ?? problem} />
            {again && <span className="text-muted-foreground text-xs">Same chart again</span>}
            {feedback.rating === 'pick' && !second && (
              <span className="text-muted-foreground text-xs">Pair collected</span>
            )}
            {code && pinned && (
              <>
                <span className="flex items-center gap-1 text-muted-foreground text-xs">
                  <CheckIcon className="size-3.5" />
                  On the dashboard
                </span>
                <Button
                  className="text-muted-foreground"
                  disabled={pinning}
                  onClick={() => void removeFromDashboard()}
                  size="sm"
                  title="Take this chart off the dashboard"
                  variant="ghost"
                >
                  Remove
                </Button>
              </>
            )}
            {code && turnId && !pinned && (
              <Button
                className="gap-1.5 text-muted-foreground"
                disabled={pinning}
                onClick={() => void addToDashboard()}
                size="sm"
                title="Keep this chart on the dashboard"
                variant="ghost"
              >
                <LayoutDashboardIcon />
                Add to dashboard
              </Button>
            )}
            {code && (
              <Button
                className="gap-1.5 text-muted-foreground"
                disabled={!feedback.ready || drawing || retrying || Boolean(second)}
                onClick={() => void regenerate()}
                size="sm"
                variant="ghost"
              >
                <RefreshCwIcon className={drawing ? 'animate-spin' : undefined} />
                {drawing ? 'Drawing...' : 'Regenerate'}
              </Button>
            )}
            <Thumbs
              busy={feedback.busy}
              disabled={!feedback.ready}
              onRate={(next) => void feedback.rate(next)}
              rating={feedback.rating}
              subject="chart"
            />
          </span>
        }
        output={chart}
      />
    </ChartCard>
  )
}

/** One chart in the transcript: the title, the chart itself, and the query behind it on demand. */
export function ChartToolStep({
  part,
  turnId,
  rating,
  narration,
}: {
  part: ChartToolPart
  turnId?: string
  rating?: PreferenceRating
  /** The turn's thinking so far, which is where the sub-agent narrates its steps. */
  narration?: string
}) {
  if (part.state === 'output-error') {
    return (
      <ChartCard>
        <ChartCardHeader title="Chart failed" />
        <div className="px-4 pb-3">
          <FailedBody reason={part.errorText} />
        </div>
      </ChartCard>
    )
  }
  if (part.state !== 'output-available') {
    return (
      <ChartCard>
        <ChartCardHeader title={part.input?.request ?? 'Planning the chart'} />
        <RunningBody />
        <Footer narration={narration} running />
      </ChartCard>
    )
  }
  return (
    <ChartResult output={part.output} rating={rating} toolCallId={part.toolCallId} turnId={turnId} />
  )
}
