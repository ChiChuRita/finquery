import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { LayoutDashboardIcon, UndoIcon } from 'lucide-react'

import { Shimmer } from '@/components/ai-elements/shimmer'
import {
  ChartCard,
  ChartCardHeader,
  ChartFrame,
  FailedBody,
  failureLine,
  Footer,
  RunningBody,
} from '@/components/chart-tool'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import {
  dashboardChartQuery,
  dashboardPinsQuery,
  undoDashboardChart,
  type DashboardChartToolPart,
  type DashboardLineToolPart,
} from '@/lib/api'
import type { ChartLanguage } from '@/lib/chart-frame'
import { useWorkspace } from '@/lib/workspace'

/** The Undo of a change a chat made to a dashboard card.
 *
 * The card owns no state of its own: whether its own change is still the one that can be taken
 * back is the server's answer, so a reload, a second browser tab and a newer change on the same
 * chart all read the same way. That is the changeset card's pattern (`changeset-card.tsx`), and
 * "Undone" is what a card whose turn has passed says.
 */
function Undo({ cardId, callId }: { cardId: string; callId: string }) {
  const { profile } = useWorkspace()
  const queryClient = useQueryClient()
  const card = useQuery(dashboardChartQuery(profile?.id, cardId, callId))
  const undoable = card.data?.undo_call_id === callId

  const act = useMutation({
    mutationFn: () => {
      if (!profile) throw new Error('No profile is active yet.')
      return undoDashboardChart(profile.id, cardId, callId)
    },
    // Every card in every transcript that is about this chart is now wrong, not only this one,
    // so they all ask again rather than being written to one by one.
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['dashboard-chart'] })
      await queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      void queryClient.invalidateQueries(dashboardPinsQuery(profile?.id))
    },
    // A refused Undo is a card that has moved on, so ask the server what it looks like now.
    onError: () => queryClient.invalidateQueries({ queryKey: ['dashboard-chart'] }),
  })

  if (card.isPending) return null
  if (!undoable) return <span className="text-muted-foreground text-xs">Undone</span>
  return (
    <span className="flex items-center gap-2">
      <Button disabled={act.isPending} onClick={() => act.mutate()} size="sm" variant="outline">
        {act.isPending ? <Spinner /> : <UndoIcon />}
        Undo
      </Button>
      {act.error && (
        <span className="text-destructive text-xs" role="alert">
          {act.error.message}
        </span>
      )}
    </span>
  )
}

/** A chart of the dashboard, drawn inside an answer: shown, or just edited.
 *
 * The rows are the ones the card's own statement returned when the tool ran, through the same
 * guard as everything else, so the figures under it are today's.
 */
export function DashboardChartToolStep({ part }: { part: DashboardChartToolPart }) {
  if (part.state === 'output-error') {
    return (
      <ChartCard>
        <ChartCardHeader title="That chart could not be changed" />
        <div className="px-4 pb-3">
          <FailedBody reason={part.errorText} />
        </div>
      </ChartCard>
    )
  }
  if (part.state !== 'output-available') {
    return (
      <ChartCard>
        <ChartCardHeader title="Working on that chart..." />
        <RunningBody />
        {/* Keyed, so the finished card below gets a fresh Footer: the running one opens its
            details by itself, and without a remount the drawn card would inherit that. */}
        <Footer key="running" running />
      </ChartCard>
    )
  }

  const output = part.output
  const title = output.title || output.request
  const edited = output.applied === true
  return (
    <ChartCard>
      <ChartCardHeader shape={output.code ? output.shape : undefined} title={title} />
      {output.code && output.rows.length > 0 ? (
        <ChartFrame
          code={output.code}
          language={(output.language ?? 'en') as ChartLanguage}
          rows={output.rows}
          title={title}
        />
      ) : (
        <div className="px-4 pb-3">
          <FailedBody
            hint="The card on the dashboard is unchanged."
            reason={
              output.error
                ? failureLine(output.error)
                : 'The query behind this chart returns no rows right now.'
            }
          />
        </div>
      )}
      <Footer
        key="done"
        actions={
          <span className="flex items-center gap-2">
            <span className="flex items-center gap-1 text-muted-foreground text-xs">
              <LayoutDashboardIcon className="size-3.5" />
              {edited ? 'Changed on the dashboard' : 'On the dashboard'}
            </span>
            {edited && output.undo_call_id && (
              <Undo callId={part.toolCallId} cardId={output.card_id} />
            )}
          </span>
        }
        output={output}
      />
    </ChartCard>
  )
}

/** A rename or a removal: one line about a card, and the Undo that takes it back. */
export function DashboardLineToolStep({ part }: { part: DashboardLineToolPart }) {
  if (part.state === 'output-error') {
    return (
      <div className="not-prose w-full rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2">
        <p className="text-destructive text-xs">{part.errorText}</p>
      </div>
    )
  }
  if (part.state !== 'output-available') {
    return (
      <div className="not-prose w-full rounded-lg border px-3 py-2">
        <Shimmer className="text-sm" duration={1.5}>
          Changing the dashboard...
        </Shimmer>
      </div>
    )
  }
  const output = part.output
  return (
    <div className="not-prose flex w-full flex-wrap items-center justify-between gap-2 rounded-lg border px-3 py-2">
      <span className="flex min-w-0 items-center gap-2">
        <LayoutDashboardIcon aria-hidden="true" className="size-4 shrink-0 text-muted-foreground" />
        <span className="truncate text-sm">{output.say}</span>
      </span>
      <Undo callId={part.toolCallId} cardId={output.card_id} />
    </div>
  )
}
