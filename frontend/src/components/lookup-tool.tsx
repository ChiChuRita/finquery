import { AlertTriangleIcon, DatabaseZapIcon, GlobeIcon, QuoteIcon } from 'lucide-react'

import { Source, Sources, SourcesContent, SourcesTrigger } from '@/components/ai-elements/sources'
import { Step } from '@/components/tool-step'
import { Badge } from '@/components/ui/badge'
import type { LookupMerchantPart } from '@/lib/api'

const requests = (searches: number, fetches: number) =>
  [
    searches === 1 ? '1 search' : `${searches} searches`,
    fetches > 0 ? (fetches === 1 ? '1 page read' : `${fetches} pages read`) : null,
  ]
    .filter(Boolean)
    .join(', ')

/** One host, so the sources read as "wikipedia.org" rather than a full URL. */
const host = (url: string) => {
  try {
    return new URL(url).host.replace(/^www\./, '')
  } catch {
    return url
  }
}

/**
 * One web lookup in the transcript: what left the machine, what came back, and the pages it
 * relied on. The sources are the AI Elements `sources` component, so a citation looks the same
 * here as anywhere else in the app.
 *
 * The quote under the summary is the part a grader can check: it is one sentence out of a
 * snippet or a page, held to occurring there word for word by the server before it is shown,
 * and the page it was read from is a link next to "1 page read".
 */
export function LookupToolStep({ part }: { part: LookupMerchantPart }) {
  if (part.state !== 'output-available') {
    const merchant = part.state === 'input-available' ? part.input.merchant : undefined
    return (
      <Step>
        <GlobeIcon className="size-3.5 shrink-0" />
        {merchant ? `Searching the web for ${merchant}` : 'Searching the web'}
        {part.state === 'output-error' && <span className="text-destructive">{part.errorText}</span>}
      </Step>
    )
  }

  const output = part.output
  if (output.error) {
    return (
      <Step tone="error">
        <AlertTriangleIcon className="size-3.5 shrink-0" />
        <span>{output.error}</span>
      </Step>
    )
  }

  // The page whose text was read, when there was one. It is the link behind "1 page read", so
  // the claim on the card is one click from the thing it is a claim about.
  const page = output.pages.at(0) ?? null

  return (
    <div className="not-prose mb-0 flex w-full flex-col gap-2 rounded-lg border bg-muted/30 px-3 py-2.5 text-xs">
      <div className="flex flex-wrap items-center gap-2">
        {output.cached ? (
          <DatabaseZapIcon aria-hidden="true" className="size-3.5 text-primary" />
        ) : (
          <GlobeIcon aria-hidden="true" className="size-3.5 text-primary" />
        )}
        <span className="font-medium text-foreground">{output.merchant}</span>
        <span className="text-muted-foreground">
          {output.cached ? (
            'from the lookup cache of this profile, nothing left the machine'
          ) : page ? (
            <>
              {requests(output.searches, 0)},{' '}
              <a
                className="underline underline-offset-2 hover:text-foreground"
                href={page}
                rel="noreferrer noopener"
                target="_blank"
              >
                1 page read
              </a>
            </>
          ) : (
            requests(output.searches, output.fetches)
          )}
        </span>
        {output.category && (
          <Badge className="ml-auto" variant="secondary">
            {output.category}
            {output.subcategory ? ` > ${output.subcategory}` : ''}
            {/* A model that finishes without a confidence leaves it at zero, and a zero percent
                badge next to a confident summary reads worse than no percentage at all. A
                capped confidence is not a percentage the sources earned either: nothing that
                came back named this merchant, so the card says so in words. */}
            {output.capped ? ' · unsure' : output.confidence > 0 ? ` · ${Math.round(output.confidence * 100)}%` : ''}
          </Badge>
        )}
      </div>
      {output.summary && <p className="text-foreground">{output.summary}</p>}
      {output.evidence && (
        <figure className="m-0 flex gap-2 border-l-2 border-primary/40 pl-2">
          <QuoteIcon aria-hidden="true" className="mt-0.5 size-3 shrink-0 text-muted-foreground" />
          <div>
            <blockquote className="m-0 border-0 p-0 text-foreground not-italic">{output.evidence}</blockquote>
            {output.evidence_url && (
              <figcaption className="mt-0.5 text-muted-foreground">
                <a
                  className="underline underline-offset-2 hover:text-foreground"
                  href={output.evidence_url}
                  rel="noreferrer noopener"
                  target="_blank"
                >
                  {host(output.evidence_url)}
                </a>
              </figcaption>
            )}
          </div>
        </figure>
      )}
      {output.capped && (
        <p className="text-muted-foreground">
          Nothing that came back names this merchant by name, so this is what the web says about
          the words in it and not certainly about this shop.
        </p>
      )}
      {/* The audit story of this feature is only true if it is legible, and the transcript is
          where the user is looking when it happens. A cache hit says it in the line above. */}
      {!output.cached && (
        <p className="text-muted-foreground">
          Only the token <span className="font-medium">{output.merchant}</span> left this machine:
          no amount, no date, no account number and no name. Settings, under Web lookup, lists
          every request that has ever gone out.
        </p>
      )}
      {output.sources.length > 0 && (
        <Sources className="mb-0">
          <SourcesTrigger count={output.sources.length} />
          <SourcesContent>
            {output.sources.map((source) => (
              <Source href={source.url} key={source.url} title={source.title || host(source.url)}>
                <span className="block max-w-md truncate font-medium">{source.title || source.url}</span>
                <span className="shrink-0 text-muted-foreground">{host(source.url)}</span>
              </Source>
            ))}
          </SourcesContent>
        </Sources>
      )}
    </div>
  )
}
