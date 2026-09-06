# Elective: self-controlled web search

**Claim.** When a merchant is unknown, the assistant searches the web itself, decides how many
searches and page reads it needs, visits a page and quotes it, and only a scrubbed merchant
token ever leaves the machine.

## The loop

1. **Scrub.** The booking text becomes a merchant token: legal forms decide "business" first
   (GmbH, AG, e.V., ...), then a list of the two hundred most common German given names refuses
   anything that reads like a person, then the two-word rule. "ANNA WEBER" is refused; "Sixt GmbH
   & Co Autovermietung KG" becomes `sixt`. Amounts, dates, IBANs never enter the token.
2. **Decide.** The fast-slot model gets the token and what it has seen so far and answers with
   one decision: `search` (with its own query), `fetch` (a URL from the hits) or `finish`, with
   reasoning and a confidence. Budget: four searches, three page reads.
3. **Floors in code.** A finish before any search is refused once. When a hit's host contains
   the token or is a Wikipedia article about it, the loop fetches that page before it may
   finish. A search backend failure is retried once without charging the budget.
4. **Read.** A fetch is one GET (10 seconds, 300 kB, one same-host redirect), reduced to text,
   2,000 characters of which reach the next decision. Every request is written to the outbound
   journal before it is sent; the journal is shown in Settings.
5. **Finish.** The answer carries a summary, a category suggestion, a confidence and an
   `evidence` quote that must occur verbatim in what was read. Confidence is capped at 0.6 when
   no source's title or host names the merchant. The result is cached per profile, so a second
   question leaves nothing.

## Who calls it

The chat tool (`lookup_merchant`), the categorizer at import (a deduplicated batch of the
busiest unknown merchants), and receipt headers (the store's name and category for a draft).
Not query, chart, memory or statement extraction: the numbers invariant forbids web figures, and
a statement page carries data that may not leave.

## Decisions

- The floors are code, not prompt: a strong hosted model answered from memory and never
  searched; the elective wording needs a visited page, so the code holds it to one.
- Evidence with a verbatim check: the same idea as the extraction guard, applied to text.
- Off by default, per profile, with the journal as proof of what left.

## Numbers

Review and reruns (`.scratch/finquery/reviews/weblookup-2026-09-06.md`, ticket 53 Comments): on
20 merchants, lookups without a search went from 9 to 0 and pages read from 0 to 12 after the
floors; the person rule stopped refusing 21 of 28 companies; the categorizer alone and with the
lookup both scored 96 percent on 72 unknown merchants on the hosted model, so the gain is
evidence and privacy, not raw accuracy there.

## Say

"It finds the page, reads it and quotes it, and the outbound log shows the only thing that left:
a merchant token. Ask it about Vogtlandbahn, not about Lidl."
