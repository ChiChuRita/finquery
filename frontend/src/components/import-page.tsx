import { ImportsList } from '@/components/imports-list'
import { DocumentPage } from '@/components/page'

/** The Import page: an overview of what was imported, and nothing that imports.
 *
 * Every file goes into the chat composer, because every question a file raises (which column is
 * the amount, is this booking one you already have, what is this merchant) is a Question card in
 * a conversation. A second place to import would be a second place to answer them.
 */
export function ImportPage() {
  return (
    <DocumentPage
      description="What each file you dropped into a chat brought in, and what is still open about it."
      title="Imports"
    >
      <ImportsList />
    </DocumentPage>
  )
}
