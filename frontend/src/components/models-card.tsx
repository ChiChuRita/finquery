import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangleIcon, CheckIcon, DownloadIcon, XIcon } from 'lucide-react'
import { useState } from 'react'

import { Shimmer } from '@/components/ai-elements/shimmer'
import { Button } from '@/components/ui/button'
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

const SLOT_LABEL: Record<string, string> = { fast: 'Gemma 4 E4B', quality: 'Qwen3.5 9B' }

const gigabytes = (bytes: number) => `${(bytes / 1e9).toFixed(2)} GB`

function FileRow({ file }: { file: ModelFile }) {
  const percent = file.size > 0 ? Math.min(100, Math.round((file.downloaded / file.size) * 100)) : 0
  const busy = file.state === 'downloading' || file.state === 'verifying'

  return (
    <li className="grid grid-cols-[1fr_auto] items-center gap-x-3 gap-y-1 py-1.5">
      <div className="flex min-w-0 items-center gap-2">
        {file.state === 'ready' ? (
          <CheckIcon aria-hidden="true" className="size-3.5 shrink-0 text-emerald-600 dark:text-emerald-500" />
        ) : file.state === 'error' ? (
          <AlertTriangleIcon aria-hidden="true" className="size-3.5 shrink-0 text-destructive" />
        ) : busy ? (
          <Spinner className="size-3.5 shrink-0 text-muted-foreground" />
        ) : (
          <DownloadIcon aria-hidden="true" className="size-3.5 shrink-0 text-muted-foreground" />
        )}
        <span className="truncate font-mono text-xs">{file.filename}</span>
        <span className="shrink-0 text-[11px] text-muted-foreground">{file.kind}</span>
      </div>
      <span className="text-right text-[11px] text-muted-foreground tabular-nums">
        {file.state === 'ready'
          ? gigabytes(file.size)
          : file.state === 'error'
            ? 'failed'
            : file.state === 'verifying'
              ? 'checking a parked copy'
              : `${percent}% of ${gigabytes(file.size)}`}
      </span>
      {file.state !== 'ready' && (
        <div className="col-span-2 h-1 overflow-hidden rounded-full bg-muted" role="progressbar" aria-valuenow={percent}>
          <div
            className={cn('h-full rounded-full transition-[width] duration-300', file.state === 'error' ? 'bg-destructive' : 'bg-primary')}
            style={{ width: `${file.state === 'error' ? 100 : percent}%` }}
          />
        </div>
      )}
      {file.error && <p className="col-span-2 text-[11px] text-destructive">{file.error}</p>}
      {file.state === 'ready' && file.source && (
        <p className="col-span-2 truncate text-[11px] text-muted-foreground">from {file.source}</p>
      )}
    </li>
  )
}

function SlotBlock({ model }: { model: SlotModel }) {
  return (
    <div className="rounded-lg border p-3">
      <div className="flex items-baseline justify-between gap-3">
        <div className="min-w-0">
          <p className="font-medium text-sm">
            {SLOT_LABEL[model.slot] ?? model.slot}
            <span className="ml-2 font-normal font-mono text-muted-foreground text-xs">{model.name}</span>
          </p>
          <p className="text-[11px] text-muted-foreground">
            {model.slot} slot
            {model.n_ctx ? ` - ${(model.n_ctx / 1024).toFixed(0)}k context` : ''}
            {model.n_ctx ? (model.loaded ? ` - resident, loaded in ${model.load_seconds}s` : ' - loads on first use') : ''}
          </p>
        </div>
        <span
          className={cn(
            'shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium',
            model.loaded
              ? 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-400'
              : model.ready
                ? 'bg-muted text-muted-foreground'
                : 'bg-amber-500/10 text-amber-700 dark:text-amber-400',
          )}
        >
          {model.loaded ? 'resident' : model.ready ? 'on disk' : 'incomplete'}
        </span>
      </div>
      {model.files.length > 0 && <ul className="mt-2 divide-y">{model.files.map((f) => <FileRow file={f} key={f.filename} />)}</ul>}
    </div>
  )
}

function CheckReport({ report }: { report: SanityReport }) {
  return (
    <div className="rounded-lg border p-3 text-xs">
      <p className="font-medium text-sm">
        {report.ok ? '✓' : '✕'} {SLOT_LABEL[report.slot] ?? report.slot}
        <span className="ml-2 font-normal font-mono text-muted-foreground">{report.model}</span>
      </p>
      {report.error && <p className="mt-1 text-destructive">{report.error}</p>}
      <ul className="mt-2 space-y-1">
        {report.checks.map((check) => (
          <li className="flex items-start gap-2" key={check.name}>
            {check.ok ? (
              <CheckIcon aria-hidden="true" className="mt-0.5 size-3.5 shrink-0 text-emerald-600 dark:text-emerald-500" />
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
    <section aria-labelledby="models-heading" className="rounded-xl border bg-card p-4 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-heading font-semibold text-base" id="models-heading">
            Models
          </h2>
          <p className="text-muted-foreground text-xs">
            Provider <span className="font-mono">{data.provider}</span>
            {local
              ? ' - Gemma 4 E4B and Qwen3.5 9B in this process through llama.cpp'
              : ' - hosted, nothing to download'}
          </p>
        </div>
        {local && (
          <div className="flex gap-2">
            <Button disabled={!missing || data.downloading} onClick={() => download.mutate()} size="sm" variant="outline">
              {data.downloading ? <Spinner /> : <DownloadIcon />}
              {data.downloading ? 'Downloading' : missing ? 'Download missing files' : 'All files on disk'}
            </Button>
            <Button disabled={missing || check.isPending} onClick={() => check.mutate()} size="sm">
              {check.isPending && <Spinner />}
              {check.isPending ? 'Checking both models' : 'Run sanity check'}
            </Button>
          </div>
        )}
      </div>

      <div className="mt-3 space-y-2">
        {data.models.map((model) => (
          <SlotBlock key={model.slot} model={model} />
        ))}
      </div>

      {local && (
        <div className="mt-3">
          <p className="font-medium text-xs">Adapters</p>
          <ul className="mt-1 space-y-0.5">
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
        <div className="mt-3 space-y-2">
          <p className="font-medium text-xs">Sanity check</p>
          {reports.map((report) => (
            <CheckReport key={report.slot} report={report} />
          ))}
        </div>
      )}
    </section>
  )
}
