import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckIcon, FileTextIcon, GlobeIcon, SearchIcon, ShieldCheckIcon } from 'lucide-react'

import { Shimmer } from '@/components/ai-elements/shimmer'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { outboundLogQuery, patchSettings, settingsQuery, type OutboundEntry } from '@/lib/api'
import { useWorkspace } from '@/lib/workspace'

const time = new Intl.DateTimeFormat('en-GB', { dateStyle: 'medium', timeStyle: 'short' })

function LogRow({ entry }: { entry: OutboundEntry }) {
  const ok = entry.status === 'ok'
  return (
    <li className="grid grid-cols-[auto_1fr_auto] items-center gap-x-2.5 py-1.5">
      {entry.kind === 'search' ? (
        <SearchIcon aria-hidden="true" className="size-3.5 shrink-0 text-muted-foreground" />
      ) : (
        <FileTextIcon aria-hidden="true" className="size-3.5 shrink-0 text-muted-foreground" />
      )}
      <span className="min-w-0 truncate font-mono text-xs" title={entry.target}>
        {entry.target}
      </span>
      <span className="shrink-0 text-[11px] text-muted-foreground tabular-nums">
        {time.format(new Date(entry.created_at))}
      </span>
      <span className="col-start-2 flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
        <span>
          merchant token <span className="font-mono">{entry.merchant_token}</span>
        </span>
        <span className={ok ? 'text-emerald-700 dark:text-emerald-400' : 'text-amber-700 dark:text-amber-400'}>
          {ok ? <CheckIcon aria-hidden="true" className="mr-0.5 inline size-3" /> : null}
          {entry.status}
        </span>
      </span>
    </li>
  )
}

/**
 * The web lookup switch and the outbound log: the two halves of the privacy claim.
 *
 * Off by default. While it is off the assistant has no lookup tool at all and this log stays
 * empty, which is what makes "nothing left my machine" checkable rather than promised.
 */
export function WebLookupCard() {
  const queryClient = useQueryClient()
  const { profile } = useWorkspace()
  const settings = useQuery(settingsQuery(profile?.id))
  const log = useQuery(outboundLogQuery(profile?.id))

  const toggle = useMutation({
    mutationFn: (on: boolean) => patchSettings(profile?.id as string, { web_lookup_enabled: on }),
    onSuccess: (next) => {
      queryClient.setQueryData(settingsQuery(profile?.id).queryKey, next)
      void queryClient.invalidateQueries(outboundLogQuery(profile?.id))
    },
  })

  const enabled = settings.data?.web_lookup_enabled ?? false
  const entries = log.data ?? []

  return (
    <section aria-labelledby="web-lookup-heading" className="rounded-xl border bg-card p-4 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="font-heading font-semibold text-base" id="web-lookup-heading">
            Web lookup
          </h2>
          <p className="max-w-xl text-muted-foreground text-xs">
            Lets the assistant search the web for a merchant it does not recognize. Only a scrubbed
            merchant name is ever sent: no amounts, no dates, no account numbers, and a booking whose
            merchant reads as a person is refused. Every request is logged below before it is sent.
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Label className="text-xs" htmlFor="web-lookup-switch">
            {enabled ? 'On' : 'Off'}
          </Label>
          <Switch
            aria-label="Web lookup"
            checked={enabled}
            disabled={settings.isPending || toggle.isPending || !profile}
            id="web-lookup-switch"
            onCheckedChange={(next) => toggle.mutate(next)}
          />
        </div>
      </div>

      {toggle.error && (
        <p className="mt-3 text-destructive text-xs" role="alert">
          The switch could not be changed: {String(toggle.error)}
        </p>
      )}

      <div className="mt-4">
        <p className="flex items-center gap-1.5 font-medium text-xs">
          {entries.length === 0 ? <ShieldCheckIcon className="size-3.5 text-emerald-600" /> : <GlobeIcon className="size-3.5" />}
          Outbound log
          <span className="font-normal text-muted-foreground">
            {entries.length === 0
              ? 'nothing has ever left this machine for this profile'
              : entries.length === 1
                ? '1 request'
                : `${entries.length} requests, newest first`}
          </span>
        </p>
        {log.isPending ? (
          <Shimmer className="mt-2 text-xs">Loading the outbound log...</Shimmer>
        ) : (
          entries.length > 0 && <ul className="mt-1 divide-y">{entries.map((entry) => <LogRow entry={entry} key={entry.id} />)}</ul>
        )}
      </div>
    </section>
  )
}
