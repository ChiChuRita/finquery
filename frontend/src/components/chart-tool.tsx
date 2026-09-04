import { ChartColumnIcon, ChevronDownIcon, ThumbsDownIcon, ThumbsUpIcon } from 'lucide-react'
import { useEffect, useRef, useState, type ReactNode } from 'react'

import { Shimmer } from '@/components/ai-elements/shimmer'
import { ErrorSection, RowsTable, Section, SqlSection, rowLabel } from '@/components/query-result'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import type { ChartToolOutput, ChartToolPart } from '@/lib/api'
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

/** Thumbs live here from ticket 15 on; the space is reserved so the card does not move later. */
function RatingPlaceholder() {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="flex items-center gap-0.5">
          <Button className="text-muted-foreground" disabled size="icon-xs" variant="ghost">
            <ThumbsUpIcon />
          </Button>
          <Button className="text-muted-foreground" disabled size="icon-xs" variant="ghost">
            <ThumbsDownIcon />
          </Button>
        </span>
      </TooltipTrigger>
      <TooltipContent>Was this chart useful? Rating arrives with the feedback page.</TooltipContent>
    </Tooltip>
  )
}

/** The audit trail under every chart: what was asked, what ran and the rows it drew. */
function Footer({ output }: { output: ChartToolOutput }) {
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
        <RatingPlaceholder />
      </div>
      <CollapsibleContent className="space-y-4 border-t px-4 pt-3 pb-4">
        <Section label="Request">
          <p className="text-sm">{output.request}</p>
          {output.plan && <p className="text-muted-foreground text-sm">{output.plan}</p>}
        </Section>
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

/** One chart in the transcript: the title, the chart itself, and the query behind it on demand. */
export function ChartToolStep({ part }: { part: ChartToolPart }) {
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

  const output = part.output
  return (
    <Card>
      <Header shape={output.shape} title={output.title || output.request} />
      {output.code && !output.error ? (
        <ChartFrame code={output.code} rows={output.rows} title={output.title || output.request} />
      ) : (
        <div className="px-4 pb-2">
          <ErrorSection message={output.error ?? 'The chart could not be drawn.'} />
        </div>
      )}
      <Footer output={output} />
    </Card>
  )
}
