import type { ReactNode } from 'react'

/** The shell of a page that reads top to bottom: Imports, Memory, Feedback, Settings.
 *
 * One heading size, one subtitle, one column width and one gap to the first section, so the
 * four pages read as one product. The chat and the Transactions page are workspaces with a
 * compact bar instead, and they share theirs the same way (`PageBar`).
 */
export function DocumentPage({
  title,
  description,
  children,
}: {
  title: string
  description: string
  children: ReactNode
}) {
  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto w-full max-w-3xl px-6 py-10">
        <h1 className="font-heading font-semibold text-2xl tracking-tight">{title}</h1>
        <p className="mt-1 text-muted-foreground text-sm">{description}</p>
        <div className="mt-6 flex flex-col gap-6">{children}</div>
      </div>
    </div>
  )
}

/** The compact header of a workspace page: the title, a caption beside it, actions at the end. */
export function PageBar({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <header className="flex h-12 shrink-0 items-center gap-3 border-b px-6">
      <h1 className="min-w-0 truncate font-heading font-semibold text-sm" title={title}>
        {title}
      </h1>
      {children}
    </header>
  )
}
