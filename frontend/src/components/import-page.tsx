import { ImportsList } from '@/components/imports-list'

/** The Import page: an overview of what was imported, and nothing that imports.
 *
 * Every file goes into the chat composer, because every question a file raises (which column is
 * the amount, is this booking one you already have, what is this merchant) is a Question card in
 * a conversation. A second place to import would be a second place to answer them.
 */
export function ImportPage() {
  return (
    <div className="flex h-full flex-col overflow-y-auto">
      <header className="flex h-14 shrink-0 items-center gap-3 border-b px-6">
        <h1 className="font-heading font-semibold text-sm">Imports</h1>
        <p className="truncate text-muted-foreground text-xs">
          What each file you dropped into a chat brought in, and what is still open about it.
        </p>
      </header>

      <div className="mx-auto w-full max-w-4xl px-6 py-6">
        <ImportsList />
      </div>
    </div>
  )
}
