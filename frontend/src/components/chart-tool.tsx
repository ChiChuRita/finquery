import { ChartColumnIcon, ChevronDownIcon, RefreshCwIcon } from 'lucide-react'
import { useEffect, useRef, useState, type ReactNode } from 'react'

import { Shimmer } from '@/components/ai-elements/shimmer'
import { FeedbackError, PairGrid, PairSide, Thumbs, useFeedback } from '@/components/feedback'
import { ErrorSection, RowsTable, Section, SqlSection, rowLabel } from '@/components/query-result'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { chartAlternative, type ChartToolOutput, type ChartToolPart, type PreferenceRating } from '@/lib/api'
import { useWorkspace } from '@/lib/workspace'
import {
  CARD_SOURCE,
  CHART_HEIGHT,
  FRAME_URL,
  isFrameMessage,
  type ChartFrameTheme,
  type ChartRow,
} from '@/lib/chart-frame'

const SHAPE_LABELS: Record<string, string> = {
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
function failureLine(error: string): string {
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

/** One chart, hosted in a sandboxed frame that owns React and TanStack Charts. */
function ChartFrame({ title, code, rows }: { title: string; code: string; rows: ChartRow[] }) {
  const frame = useRef<HTMLIFrameElement>(null)
  const [ready, setReady] = useState(false)
  const [live, setLive] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // The theme toggle flips a class on <html>; watching it is independent of effect ordering.
  const [themeChanges, setThemeChanges] = useState(0)

  useEffect(() => {
    const observer = new MutationObserver(() => setThemeChanges((count) => count + 1))
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    const onMessage = (event: MessageEvent) => {
      if (event.source !== frame.current?.contentWindow || !isFrameMessage(event.data)) return
      if (event.data.kind === 'hello') setReady(true)
      if (event.data.kind === 'ready') {
        setError(null)
        setLive(true)
      }
      if (event.data.kind === 'error') {
        setError(event.data.message)
        setLive(false)
      }
    }
    window.addEventListener('message', onMessage)
    return () => window.removeEventListener('message', onMessage)
  }, [])

  useEffect(() => {
    if (!ready) return
    frame.current?.contentWindow?.postMessage(
      { source: CARD_SOURCE, kind: 'render', title, code, rows, theme: readTheme() },
      '*',
    )
  }, [ready, title, code, rows, themeChanges])

  return (
    <div className="relative" style={{ height: CHART_HEIGHT }}>
      <iframe
        className="h-full w-full border-0"
        // The frame's "hello" can arrive before React has run this component's effects, so the
        // load event is the reliable trigger and the message is only a second chance.
        onLoad={() => setReady(true)}
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
        <div className="absolute inset-0 flex items-center justify-center px-6">
          <p className="rounded-md bg-destructive/10 px-3 py-2 text-center text-destructive text-sm">
            This chart could not be drawn: {error}
          </p>
        </div>
      )}
    </div>
  )
}

/** The audit trail under every chart: what was asked, what ran and the rows it drew. */
function Footer({ output, actions }: { output: ChartToolOutput; actions: ReactNode }) {
  const [open, setOpen] = useState(false)
  return (
    <Collapsible onOpenChange={setOpen} open={open}>
      <div className="flex items-center justify-between gap-2 border-t px-2 py-1.5">
        <CollapsibleTrigger asChild>
          <Button className="gap-1.5 text-muted-foreground" size="sm" variant="ghost">
            <ChevronDownIcon className={open ? 'rotate-180 transition-transform' : 'transition-transform'} />
            {output.sql ? `SQL and ${rowLabel(output.row_count)}` : 'Details'}
          </Button>
        </CollapsibleTrigger>
        {actions}
      </div>
      <CollapsibleContent className="space-y-4 border-t px-4 pt-3 pb-4">
        <Section label="Request">
          <p className="text-sm">{output.request}</p>
          {output.plan && <p className="text-muted-foreground text-sm">{output.plan}</p>}
        </Section>
        {output.error && (
          // The card says the failure in one line; what was quoted into it, code and all, is here.
          <Section label="Why it failed">
            <p className="whitespace-pre-wrap break-words rounded-md bg-muted px-3 py-2 font-mono text-muted-foreground text-xs">
              {output.error}
            </p>
          </Section>
        )}
        {output.notes.length > 0 && (
          <Section label="Repairs">
            <ul className="space-y-1 text-muted-foreground text-sm">
              {output.notes.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          </Section>
        )}
        {output.sql && <SqlSection sql={output.sql} />}
        {output.row_count > 0 && (
          <Section label={`Rows · ${rowLabel(output.row_count)}`}>
            <RowsTable columns={output.columns} rows={output.rows} />
          </Section>
        )}
      </CollapsibleContent>
    </Collapsible>
  )
}

function Card({ children }: { children: ReactNode }) {
  return (
    <div className="w-full overflow-hidden rounded-xl border bg-card" data-slot="chart-card">
      {children}
    </div>
  )
}

function Header({ title, shape }: { title: string; shape?: string }) {
  return (
    <div className="flex items-start justify-between gap-3 px-4 pt-3 pb-2">
      <h3 className="font-medium text-sm leading-snug">{title}</h3>
      {shape && (
        <Badge className="shrink-0 gap-1 font-normal text-muted-foreground" variant="outline">
          <ChartColumnIcon className="size-3" />
          {SHAPE_LABELS[shape] ?? shape}
        </Badge>
      )}
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

  const title = output.title || output.request
  // The definition to draw, or null when this chart failed and the card shows the reason.
  const code = output.error ? null : output.code

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
    <Card>
      <Header shape={output.shape} title={title} />
      {code && second?.code ? (
        <div className="px-3 pb-3">
          <PairGrid>
            <PairSide
              disabled={feedback.busy}
              label="The first chart"
              note={SHAPE_LABELS[output.shape] ?? output.shape}
              onPick={() => void pick('original')}
              picked={picked === 'original'}
            >
              <ChartFrame code={code} rows={output.rows} title={title} />
            </PairSide>
            <PairSide
              disabled={feedback.busy}
              label="Drawn again"
              note={SHAPE_LABELS[second.shape] ?? second.shape}
              onPick={() => void pick('candidate')}
              picked={picked === 'candidate'}
            >
              <ChartFrame code={second.code} rows={second.rows} title={second.title || title} />
            </PairSide>
          </PairGrid>
          <p className="pt-2 text-muted-foreground text-xs">
            {picked
              ? 'Stored as a preference pair. Both charts drew the rows of the same query.'
              : 'Both charts drew the rows of the same query. Pick the better one.'}
          </p>
        </div>
      ) : code ? (
        <ChartFrame code={code} rows={output.rows} title={title} />
      ) : (
        <div className="space-y-2 px-4 pb-3">
          <ErrorSection message={failureLine(output.error ?? '')} />
          <p className="text-muted-foreground text-xs">
            Nothing was drawn. The whole reason, the plan and the query it tried are under Details.
          </p>
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
            {code && (
              <Button
                className="gap-1.5 text-muted-foreground"
                disabled={!feedback.ready || drawing || Boolean(second)}
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
        output={output}
      />
    </Card>
  )
}

/** One chart in the transcript: the title, the chart itself, and the query behind it on demand. */
export function ChartToolStep({
  part,
  turnId,
  rating,
}: {
  part: ChartToolPart
  turnId?: string
  rating?: PreferenceRating
}) {
  if (part.state === 'output-error') {
    return (
      <Card>
        <Header title="Chart failed" />
        <div className="px-4 pb-4">
          <ErrorSection message={part.errorText} />
        </div>
      </Card>
    )
  }
  if (part.state !== 'output-available') {
    return (
      <Card>
        <Header title={part.input?.request ?? 'Planning the chart'} />
        <div className="flex items-center gap-2 px-4 pb-4">
          <Shimmer className="text-muted-foreground text-sm">Planning, querying, drawing...</Shimmer>
        </div>
      </Card>
    )
  }
  return (
    <ChartResult output={part.output} rating={rating} toolCallId={part.toolCallId} turnId={turnId} />
  )
}
