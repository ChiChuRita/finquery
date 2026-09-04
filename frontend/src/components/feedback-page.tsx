import { useQuery } from '@tanstack/react-query'
import { ChartColumnIcon, DownloadIcon, MessageSquareIcon, ScaleIcon, ThumbsDownIcon, ThumbsUpIcon } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  preferencesExportUrl,
  preferencesQuery,
  type PreferenceKind,
  type PreferenceRating,
  type PreferenceRecord,
} from '@/lib/api'
import { formatDateTime } from '@/lib/format'
import { useWorkspace } from '@/lib/workspace'

const KIND = {
  answer: { label: 'Answer', icon: MessageSquareIcon },
  chart: { label: 'Chart', icon: ChartColumnIcon },
} satisfies Record<PreferenceKind, { label: string; icon: typeof MessageSquareIcon }>

const RATING = {
  up: { label: 'Useful', icon: ThumbsUpIcon, className: 'text-primary' },
  down: { label: 'Not useful', icon: ThumbsDownIcon, className: 'text-destructive' },
  pick: { label: 'Picked', icon: ScaleIcon, className: 'text-foreground' },
} satisfies Record<PreferenceRating, { label: string; icon: typeof ThumbsUpIcon; className: string }>

/** One record: what was asked, what the user said about the answer, and when. */
function Row({ record }: { record: PreferenceRecord }) {
  const kind = KIND[record.kind]
  const rating = RATING[record.rating]
  const KindIcon = kind.icon
  const RatingIcon = rating.icon
  return (
    <li className="flex items-start gap-3 px-4 py-3">
      <Badge className="mt-0.5 shrink-0 gap-1 font-normal" variant="outline">
        <KindIcon className="size-3" />
        {kind.label}
      </Badge>
      <div className="min-w-0 flex-1">
        <p className="line-clamp-2 text-sm" title={record.prompt}>
          {record.prompt}
        </p>
        <p className="pt-1 text-[11px] text-muted-foreground">
          {formatDateTime(record.created_at)} &middot; {record.model_slot} slot
          {record.paired && ' · chosen and rejected'}
        </p>
      </div>
      <span className={`mt-0.5 flex shrink-0 items-center gap-1.5 text-xs ${rating.className}`}>
        <RatingIcon className="size-3.5" />
        {rating.label}
      </span>
    </li>
  )
}

/** What the ratings have collected so far, and the JSONL a training run reads. */
export function FeedbackPage() {
  const { profile } = useWorkspace()
  const { data: records } = useQuery(preferencesQuery(profile?.id))
  const pairs = (records ?? []).filter((record) => record.paired).length

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto w-full max-w-3xl px-6 py-10">
        <h1 className="font-heading font-semibold text-2xl tracking-tight">Feedback</h1>
        <p className="mt-1 text-muted-foreground text-sm">
          Every thumb, every chart you picked and every second answer you preferred is kept as a preference record:
          the prompt, the output you kept and the one you refused. The export is the training set for the two
          fine-tuned sub-agents.
        </p>

        <section className="mt-6 space-y-3">
          <div className="flex items-baseline justify-between gap-3">
            <h2 className="font-heading font-semibold text-sm">Collected records</h2>
            <div className="flex items-center gap-3">
              {records && records.length > 0 && (
                <span className="text-muted-foreground text-xs">
                  {records.length === 1 ? '1 record' : `${records.length} records`}
                  {pairs > 0 && `, ${pairs} with both sides`}
                </span>
              )}
              {profile && records && records.length > 0 ? (
                // A plain link: the browser writes the file, so nothing is buffered in the app.
                <Button asChild size="sm" variant="outline">
                  <a download href={preferencesExportUrl(profile.id)}>
                    <DownloadIcon className="size-4" />
                    Export JSONL
                  </a>
                </Button>
              ) : (
                <Button disabled size="sm" variant="outline">
                  <DownloadIcon className="size-4" />
                  Export JSONL
                </Button>
              )}
            </div>
          </div>

          {!records || records.length === 0 ? (
            <div className="flex items-center gap-3 rounded-xl border border-dashed px-4 py-6 text-muted-foreground text-sm">
              <ThumbsUpIcon className="size-4 shrink-0" />
              Nothing rated yet. Use the thumbs under an answer or a chart, regenerate a chart and pick the better
              one, and the records appear here.
            </div>
          ) : (
            <ul className="divide-y rounded-xl border">
              {records.map((record) => (
                <Row key={record.id} record={record} />
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  )
}
