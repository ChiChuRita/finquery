import { ThumbsDownIcon, ThumbsUpIcon } from 'lucide-react'
import { useState } from 'react'

import { MessageAction, MessageActions, MessageResponse } from '@/components/ai-elements/message'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import {
  answerAlternative,
  ratePreference,
  storePreferencePair,
  type AlternativeAnswer,
  type PairCandidate,
  type PreferenceRating,
} from '@/lib/api'
import { useWorkspace } from '@/lib/workspace'

/** One thumb, one pick: everything a card or a message needs to leave a preference record.
 *
 * The turn is the identity of what is being rated, and `target` names the chart inside it, so
 * the same hook serves the answer toolbar and every chart card. A record is replaced rather
 * than added by a second click, so the state here is simply the last thing the user said.
 */
export function useFeedback(turnId: string | undefined, target: string | null, initial?: PreferenceRating) {
  const { profile } = useWorkspace()
  const [rating, setRating] = useState<PreferenceRating | undefined>(initial)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string>()

  const guarded = async (work: () => Promise<void>) => {
    if (!profile || !turnId || busy) return
    setBusy(true)
    setError(undefined)
    try {
      await work()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'That did not work.')
    } finally {
      setBusy(false)
    }
  }

  return {
    rating,
    busy,
    error,
    /** Ready once the turn is stored, which is when the stream has ended. */
    ready: Boolean(profile && turnId),
    rate: (next: 'up' | 'down') =>
      guarded(async () => {
        await ratePreference(profile!.id, { turn_id: turnId!, target, rating: next })
        setRating(next)
      }),
    pick: (picked: 'original' | 'candidate', candidate: PairCandidate) =>
      guarded(async () => {
        await storePreferencePair(profile!.id, { turn_id: turnId!, target, picked, candidate })
        setRating('pick')
      }),
  }
}

const QUESTION = { response: 'Was this response useful?', chart: 'Was this chart useful?' }

// A screen reader reads the name, not the tooltip, so the name has to be the verdict itself:
// "Yes. Was this response useful?" reads as a question being asked of the reader.
const VERDICT = {
  response: { up: 'This response was useful', down: 'This response was not useful' },
  chart: { up: 'This chart was useful', down: 'This chart was not useful' },
}

/** Thumbs up and down, in the message toolbar of an answer or the footer of a chart card. */
export function Thumbs({
  subject,
  rating,
  busy,
  disabled,
  onRate,
}: {
  subject: 'response' | 'chart'
  rating?: PreferenceRating
  busy?: boolean
  disabled?: boolean
  onRate: (rating: 'up' | 'down') => void
}) {
  const question = QUESTION[subject]
  return (
    <MessageActions className="gap-0">
      <MessageAction
        aria-pressed={rating === 'up'}
        className={cn('size-6 text-muted-foreground', rating === 'up' && 'text-primary')}
        disabled={disabled || busy}
        label={VERDICT[subject].up}
        onClick={() => onRate('up')}
        tooltip={rating === 'up' ? 'You found this useful' : question}
      >
        <ThumbsUpIcon className={cn('size-3.5', rating === 'up' && 'fill-current')} />
      </MessageAction>
      <MessageAction
        aria-pressed={rating === 'down'}
        className={cn('size-6 text-muted-foreground', rating === 'down' && 'text-destructive')}
        disabled={disabled || busy}
        label={VERDICT[subject].down}
        onClick={() => onRate('down')}
        tooltip={rating === 'down' ? 'You did not find this useful' : question}
      >
        <ThumbsDownIcon className={cn('size-3.5', rating === 'down' && 'fill-current')} />
      </MessageAction>
    </MessageActions>
  )
}

export function FeedbackError({ message }: { message?: string }) {
  if (!message) return null
  return (
    <p className="text-destructive text-xs" role="alert">
      {message}
    </p>
  )
}

/** One side of a pair: a heading, the output, and the button that keeps it. */
export function PairSide({
  label,
  note,
  picked,
  disabled,
  unavailable,
  onPick,
  children,
}: {
  label: string
  note?: string
  picked?: boolean
  disabled?: boolean
  /** Why this side cannot be picked. A chart that did not draw is not a preference. */
  unavailable?: string
  onPick: () => void
  children: React.ReactNode
}) {
  return (
    <div className={cn('flex min-w-0 flex-col rounded-lg border', picked && 'border-primary ring-1 ring-primary/30')}>
      <div className="flex items-center justify-between gap-2 border-b px-3 py-1.5">
        <span className="truncate font-medium text-xs">{label}</span>
        {note && <span className="shrink-0 text-muted-foreground text-2xs">{note}</span>}
      </div>
      <div className="min-w-0 flex-1">{children}</div>
      <div className="border-t px-3 py-2">
        {unavailable ? (
          <p className="text-center text-muted-foreground text-xs">{unavailable}</p>
        ) : (
          <Button
            // Both sides of a pair carry the same words, so the heading above them is what
            // tells a screen reader which one is being picked.
            aria-label={picked ? `Picked: ${label}` : `Pick ${label}`}
            className="w-full"
            disabled={disabled || picked}
            onClick={onPick}
            size="sm"
            variant={picked ? 'secondary' : 'outline'}
          >
            {picked ? 'Picked' : 'Pick this one'}
          </Button>
        )}
      </div>
    </div>
  )
}

/** Two outputs next to each other, each with a Pick. */
export function PairGrid({ children }: { children: React.ReactNode }) {
  return <div className="grid gap-3 md:grid-cols-2">{children}</div>
}

/** The whole feedback state of one answer: the thumbs, plus the A/B a thumbs down offers.
 *
 * The second answer is asked for on demand, never automatically: it costs a model call and it
 * only makes sense once the user has said the first one was not good.
 */
export function useAnswerFeedback(turnId: string | undefined, rating?: PreferenceRating) {
  const { profile } = useWorkspace()
  const feedback = useFeedback(turnId, null, rating)
  const [second, setSecond] = useState<AlternativeAnswer>()
  const [asking, setAsking] = useState(false)
  const [problem, setProblem] = useState<string>()
  const [picked, setPicked] = useState<'original' | 'candidate'>()

  const compare = async () => {
    if (!profile || !turnId || asking) return
    setAsking(true)
    setProblem(undefined)
    try {
      setSecond(await answerAlternative(profile.id, turnId))
      setPicked(undefined)
    } catch (cause) {
      setProblem(cause instanceof Error ? cause.message : 'A second answer could not be produced.')
    } finally {
      setAsking(false)
    }
  }

  return {
    ...feedback,
    second,
    asking,
    picked,
    problem: feedback.error ?? problem,
    compare,
    pick: async (which: 'original' | 'candidate') => {
      if (!second) return
      await feedback.pick(which, { text: second.text, tools: second.tools })
      setPicked(which)
    },
  }
}

/** The answer the user got against a second one, each with a Pick. */
export function AnswerCompare({
  original,
  second,
  picked,
  busy,
  onPick,
}: {
  original: string
  second: AlternativeAnswer
  picked?: 'original' | 'candidate'
  busy?: boolean
  onPick: (which: 'original' | 'candidate') => void
}) {
  return (
    <div className="w-full">
      <PairGrid>
        <PairSide
          disabled={busy}
          label="The answer you got"
          onPick={() => onPick('original')}
          picked={picked === 'original'}
        >
          <div className="px-3 py-2 text-sm">
            <MessageResponse>{original}</MessageResponse>
          </div>
        </PairSide>
        <PairSide
          disabled={busy}
          label="A second answer"
          note={`temperature ${second.temperature}`}
          onPick={() => onPick('candidate')}
          picked={picked === 'candidate'}
        >
          <div className="px-3 py-2 text-sm">
            <MessageResponse>{second.text}</MessageResponse>
          </div>
        </PairSide>
      </PairGrid>
      <p className="pt-1.5 text-muted-foreground text-xs">
        {picked
          ? 'Stored as a preference pair.'
          : 'The same question, answered again at a higher temperature. Pick the better one.'}
      </p>
    </div>
  )
}
