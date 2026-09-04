import type { ReactNode } from 'react'

/** One line in the transcript for a tool that has nothing to unfold: a rule, a queue, a booking. */
export function Step({ children, tone = 'muted' }: { children: ReactNode; tone?: 'muted' | 'error' }) {
  return (
    <div
      className={
        tone === 'error'
          ? 'not-prose mb-0 flex w-full items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-destructive text-xs'
          : 'not-prose mb-0 flex w-full items-center gap-2 rounded-lg border bg-muted/30 px-3 py-2 text-muted-foreground text-xs'
      }
    >
      {children}
    </div>
  )
}
