import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangleIcon, CheckIcon, DownloadIcon, XIcon } from 'lucide-react'
import { useState } from 'react'

import { Shimmer } from '@/components/ai-elements/shimmer'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { Spinner } from '@/components/ui/spinner'
import {
  modelsQuery,
  runSanityCheck,
  startModelDownload,
  type ModelFile,
  type SanityReport,
  type SlotModel,
} from '@/lib/api'
import { cn } from '@/lib/utils'

const gigabytes = (bytes: number) => `${(bytes / 1e9).toFixed(2)} GB`

function FileRow({ file }: { file: ModelFile }) {
  const percent = file.size > 0 ? Math.min(100, Math.round((file.downloaded / file.size) * 100)) : 0
  const busy = file.state === 'downloading' || file.state === 'verifying'

  return (
    <li className="grid grid-cols-[1fr_auto] items-center gap-x-3 gap-y-1 py-1.5">
      <div className="flex min-w-0 items-center gap-2">
        {file.state === 'ready' ? (
          <CheckIcon aria-hidden="true" className="size-3.5 shrink-0 text-primary" />
        ) : file.state === 'error' ? (
          <AlertTriangleIcon aria-hidden="true" className="size-3.5 shrink-0 text-destructive" />
        ) : busy ? (
          <Spinner className="size-3.5 shrink-0 text-muted-foreground" />
        ) : (
          <DownloadIcon aria-hidden="true" className="size-3.5 shrink-0 text-muted-foreground" />
        )}
        <span className="truncate font-mono text-xs">{file.filename}</span>
        <span className="shrink-0 text-2xs text-muted-foreground">{file.kind}</span>
      </div>
      <span className="text-right text-2xs text-muted-foreground tabular-nums">
        {file.state === 'ready'
          ? gigabytes(file.size)
          : file.state === 'error'
            ? 'failed'
            : file.state === 'verifying'
              ? 'checking a parked copy'
              : `${percent}% of ${gigabytes(file.size)}`}
      </span>
      {file.state !== 'ready' && (
        <Progress
          aria-label={`${file.filename} download`}
          className={cn('col-span-2', file.state === 'error' && '[&>[data-slot=progress-indicator]]:bg-destructive')}
          value={file.state === 'error' ? 100 : percent}
        />
      )}
      {file.error && <p className="col-span-2 text-2xs text-destructive">{file.error}</p>}
      {file.state === 'ready' && file.source && (
        <p className="col-span-2 truncate text-2xs text-muted-foreground">from {file.source}</p>
      )}
    </li>
  )
}

/** One slot: which model fills it and how ready it is.
 *
 * "resident" is a fact about a GGUF sitting in this process's memory, so it is only said on
 * the local provider. A hosted model is neither resident nor on disk; it is simply reachable.
 */
function SlotBlock({ model, local }: { model: SlotModel; local: boolean }) {
  const state = local ? (model.loaded ? 'resident' : model.ready ? 'on disk' : 'incomplete') : 'hosted'
  return (
    <div className="rounded-lg border p-3">
      <div className="flex items-baseline justify-between gap-3">
        <div className="min-w-0">
          <p className="font-medium text-sm">
            {model.label}
            <span className="ml-2 font-normal font-mono text-muted-foreground text-xs">{model.name}</span>
          </p>
          <p className="text-2xs text-muted-foreground">
            {model.slot} slot
            {model.n_ctx ? ` - ${(model.n_ctx / 1024).toFixed(0)}k context` : ''}
            {model.n_ctx ? (model.loaded ? ` - resident, loaded in ${model.load_seconds}s` : ' - loads on first use') : ''}
          </p>
        </div>
        <Badge className="shrink-0" variant={state === 'incomplete' ? 'warning' : state === 'on disk' ? 'secondary' : 'success'}>
          {state}
        </Badge>
      </div>
      {model.files.length > 0 && <ul className="mt-2 divide-y">{model.files.map((f) => <FileRow file={f} key={f.filename} />)}</ul>}
    </div>
  )
}

function CheckReport({ report, label }: { report: SanityReport; label: string }) {
  return (
    <div className="rounded-lg border p-3 text-xs">
      <p className="font-medium text-sm">
        {report.ok ? '✓' : '✕'} {label}
        <span className="ml-2 font-normal font-mono text-muted-foreground">{report.model}</span>
      </p>
      {report.error && <p className="mt-1 text-destructive">{report.error}</p>}
      <ul className="mt-2 flex flex-col gap-1">
        {report.checks.map((check) => (
          <li className="flex items-start gap-2" key={check.name}>
            {check.ok ? (
              <CheckIcon aria-hidden="true" className="mt-0.5 size-3.5 shrink-0 text-primary" />
            ) : (
              <XIcon aria-hidden="true" className="mt-0.5 size-3.5 shrink-0 text-destructive" />
            )}
            <span className="w-20 shrink-0 font-medium">{check.name}</span>
            <span className="w-28 shrink-0 text-muted-foreground tabular-nums">
              {check.seconds}s{check.tokens_per_second ? `, ${check.tokens_per_second} tok/s` : ''}
            </span>
            <span className="min-w-0 flex-1 text-muted-foreground">{check.detail}</span>
          </li>
        ))}
        {report.adapters.map((adapter) => (
          <li className="flex items-start gap-2 text-muted-foreground" key={adapter.name}>
            <span className="mt-0.5 size-3.5 shrink-0 text-center">-</span>
            <span className="w-20 shrink-0 font-medium">{adapter.name}</span>
            <span className="min-w-0 flex-1">{adapter.attached ? 'adapter attached' : adapter.note}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

export function ModelsCard() {
  const queryClient = useQueryClient()
  const { data, error, isPending } = useQuery(modelsQuery)
  const [reports, setReports] = useState<SanityReport[] | null>(null)

  const download = useMutation({
    mutationFn: startModelDownload,
    onSuccess: (next) => queryClient.setQueryData(modelsQuery.queryKey, next),
  })
  const check = useMutation({ mutationFn: runSanityCheck, onSuccess: (result) => setReports(result.reports) })

  if (isPending) return <Shimmer className="text-sm">Loading model status...</Shimmer>
  if (error || !data)
    return (
      <p className="text-destructive text-sm" role="alert">
        Model status could not be loaded.
      </p>
    )

  const local = data.provider === 'local'
  const missing = data.models.some((m) => !m.ready)

  return (
    <section aria-labelledby="models-heading" className="rounded-xl border bg-card p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-heading font-semibold text-base" id="models-heading">
            Models
          </h2>
          <p className="text-muted-foreground text-xs">
            Provider <span className="font-mono">{data.provider}</span>
            {local
              ? ` - ${data.models.map((model) => model.label).join(' and ')} in this process through llama.cpp`
              : ' - hosted, nothing to download'}
          </p>
        </div>
        {local && (
          <div className="flex gap-2">
            <Button disabled={!missing || data.downloading} onClick={() => download.mutate()} size="sm" variant="outline">
              {data.downloading ? <Spinner data-icon="inline-start" /> : <DownloadIcon data-icon="inline-start" />}
              {data.downloading ? 'Downloading' : missing ? 'Download missing files' : 'All files on disk'}
            </Button>
            <Button disabled={missing || check.isPending} onClick={() => check.mutate()} size="sm">
              {check.isPending && <Spinner data-icon="inline-start" />}
              {check.isPending ? 'Checking both models' : 'Run sanity check'}
            </Button>
          </div>
        )}
      </div>

      <div className="mt-3 flex flex-col gap-2">
        {data.models.map((model) => (
          <SlotBlock key={model.slot} local={local} model={model} />
        ))}
      </div>

      {local && (
        <div className="mt-3">
          <p className="font-medium text-xs">Adapters</p>
          <ul className="mt-1 flex flex-col gap-0.5">
            {data.adapters.map((adapter) => (
              <li className="flex items-center gap-2 text-xs" key={adapter.name}>
                <span className="w-14 font-medium">{adapter.name}</span>
                <span className="text-muted-foreground">
                  {adapter.present ? (
                    <>
                      ready at <span className="font-mono">{adapter.path}</span>
                    </>
                  ) : (
                    <>
                      no file at <span className="font-mono">{adapter.path}</span>, sub-agents run on the base weights
                    </>
                  )}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {check.error && (
        <p className="mt-3 text-destructive text-xs" role="alert">
          The sanity check failed to run: {String(check.error)}
        </p>
      )}
      {reports && (
        <div className="mt-3 flex flex-col gap-2">
          <p className="font-medium text-xs">Sanity check</p>
          {reports.map((report) => (
            <CheckReport
              key={report.slot}
              label={data.models.find((model) => model.slot === report.slot)?.label ?? report.slot}
              report={report}
            />
          ))}
        </div>
      )}
    </section>
  )
}
