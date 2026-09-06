import type { ReactNode } from 'react'

import { SidebarTrigger } from '@/components/ui/sidebar'
import { cn } from '@/lib/utils'

/** The sidebar toggle, at the start of every page's header. It is pulled left by the gap
 *  between the button's edge and its icon, so the icon sits on the page's content edge. */
export function PageTrigger({ className }: { className?: string }) {
  return <SidebarTrigger className={cn('-ml-1.5 text-muted-foreground', className)} />
}

/** The shell of a page that reads top to bottom: Imports, Memory, Settings.
 *
 * One heading size, one subtitle, one column width and one gap to the first section, so the
 * three pages read as one product. The chat and the Transactions page are workspaces with a
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
      <div className="mx-auto w-full max-w-3xl px-6 pt-2.5 pb-10">
        <PageTrigger />
        <h1 className="mt-5 font-heading font-semibold text-2xl tracking-tight">{title}</h1>
        <p className="mt-1 text-muted-foreground text-sm">{description}</p>
        <div className="mt-6 flex flex-col gap-6">{children}</div>
      </div>
    </div>
  )
}

/** The compact header of a workspace page: the sidebar toggle, the title, a caption beside
 *  it, actions at the end. */
export function PageBar({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <header className="flex h-12 shrink-0 items-center gap-3 border-b px-6">
      <PageTrigger />
      <h1 className="min-w-0 truncate font-heading font-semibold text-sm" title={title}>
        {title}
      </h1>
      {children}
    </header>
  )
}
