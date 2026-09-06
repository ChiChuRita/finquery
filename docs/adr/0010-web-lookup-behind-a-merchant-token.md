# ADR 0010: Web lookup is a loop the model drives behind a merchant token

Date: 2026-09-04
Status: accepted

## Context

A card payment to a shop the user does not recognize needs a web search before it can be
categorized. The product's promise is that the data stays on the machine, so the feature that
talks to the internet has to be the one part of the app whose behaviour is checkable rather than
promised. The course also asks for a self-directed search: the agent, not a fixed script,
decides how much looking is enough.

## Decision

- **Off by default, per profile.** `profile.web_lookup_enabled`, `GET`/`PATCH /api/settings`.
  `weblookup.lookups_for` is the only place that reads it and returns `None` when it is off, so
  "off" is the absence of the object rather than a branch in every caller.
- **A merchant token is the only thing that leaves.** `weblookup.scrub` starts from the merchant
  the categorizer already derives (`merchants.merchant_of`) and then removes amounts, dates,
  IBANs, card, customer and reference numbers with the labels that introduce them. A booking
  whose name reads as a person is refused outright: there is no partial token, `scrub` returns
  nothing plus the reason, and no request is made. The query the model writes goes through the
  same rule (`safe_query`) before it is sent, because a query is also a trust boundary.
- **The person rule is read in one order, and the order is the argument** (amended by ticket 53
  on the review of 2026-09-06). A legal form anywhere in the string wins first (`GmbH`, `AG`,
  `SE`, `KG`, `e.V.`, `a.G.`, `B.V.`, `& Co`): it is the strongest business signal a booking
  carries, and reading it after the form had been dropped as uninformative refused 24 companies
  out of 28 refusals. Then a list of two hundred common German given names refuses a name in
  either position, before the business-word exemption, so "Anna Bauer" is a person although
  "Bauer" ends in a trade. Only then the old count of two capitalized words. All three read the
  same string the rule always read: the counterparty, or the booking text when the counterparty
  is only the processor, so `PayPal Europe S.a.r.l.` never vouches for the friend next to it.
- **What holds the loop to the web is code, not the prompt.** A stronger model recalls instead
  of searching (34 of 82 lookups finished with no search at all, and none ever read a page), so
  the elective's claim would otherwise depend on which model is running. Four rules, each
  enforced once per lookup so a model that cannot satisfy one still answers: a finish before any
  search is handed back; a result that is the merchant's own site or a Wikipedia article about
  it is fetched by the loop itself before a finish is taken; a finish carries an `evidence`
  sentence that has to occur word for word in what the steps returned, checked the way an
  extracted figure is checked against its page; and a confidence above 0.6 is capped when no
  source's title or host carries the token, because a local name matches many real businesses.
  A search backend that failed is retried once inside the same step, which costs neither a
  model call nor a search from the budget.
- **The loop is ours, the decisions are the model's.** One step is one request to the fast slot
  with a forced single tool, `decide`: `search` with a query, `fetch` with one of the URLs it was
  shown, or `finish` with a summary, a category, a subcategory, a confidence and the sources it
  relied on. Our code executes the step, appends the observation and asks again
  (`weblookup.loop`). The budget (four searches, three page fetches) is a ceiling the model is
  told about, not a plan: it stops when it knows, which for a well-known merchant is after the
  first search.
- **Every request is written before it is sent.** `store.OutboundJournal` commits an
  `outbound_request` row (profile, kind, target, merchant token, status `sent`) on its own
  session before the call and settles the status afterwards. The loop's only route to the outside
  world goes through it, so the ordering is a property of the code. `GET /api/outbound-log` and
  the Settings card show it.
- **A merchant token leaves at most once per profile.** The result is cached in `web_lookup` by
  (profile, token) with its summary, sources, category and confidence. A lookup that reached no
  conclusion is not cached, so a rate limit does not become a permanent wrong answer.
- **The result is a placement like any other.** In the categorizer pipeline the lookup is a stage
  between the merchant dictionary and the model, feeding the same `Guess` shape, so the
  confidence threshold and the Question cards work unchanged and a merchant the lookup placed
  **at or above the threshold** never reaches the model. One it was unsure about does reach it,
  as a `web:` line under the booking text: an unsure lookup used to take the merchant off the
  batch, and the measured cost was a salary the categorizer had right at 0.90 becoming a
  Question card at 0.20 (ticket 53). On the chat agent it is the `lookup_merchant` tool,
  declared only when the switch is on (its `prepare` reads the switch per run) and rendered with
  the AI Elements `sources` component.
- **Three callers, one capability.** `Lookups.merchant` for the chat tool, `Lookups.merchants`
  for one import run (deduplicated by token, cached and refused tokens answered without a
  request, one at a time with a pause), `Lookups.store` for a receipt's printed header. One
  cache, one journal, one switch. Not the query, chart, memory, statement or mapping sub-agents:
  the first two would break the numbers invariant, and the others have nothing to ask.
- **`confidence` is the one required field of `decide`.** Every other field is optional because a
  search decision has nothing to put in it, but the observed fast model leaves an optional float
  out, and a lookup without a confidence can place nothing. So it is required and sends 0 for a
  search or a fetch, and a finish that sends 0 is handed back once for a real number.
- Search is `ddgs` (keyless, a comma-separated backend chain of duckduckgo, bing, brave, so a
  rate-limited backend is skipped rather than fatal); a fetch is one `httpx` GET with a ten
  second timeout, a 300 kB cap, standard-library HTML to text, and at most one redirect to the
  same host. Both sit behind the `WebClient` protocol, which tests replace through the app
  factory, so no test reaches the network (ADR 0003).

## Consequences

- "Nothing left my machine" is answered by a table the user can read, and the tests can assert
  the ordering (log entry before the request) and the emptiness (switch off, no calls).
- The person rule still errs towards refusing, one step further along: a two-word company with
  no legal form, no trade word and no given name in it ("ROFU Kinderland", "Blumen Riedel") is
  not looked up, and neither is a shop whose city was stripped as noise ("Fressnapf
  Köln-Ehrenfeld" becomes two words). That costs a lookup and never a name. The given-name list
  is the upgrade path this ADR named; it is now in `scrub.GIVEN_NAMES` and it fires only on the
  two-word shape, so "Hans im Glueck Burgergrill" and "Peter Pane Burgergrill" still pass.
- The four code rules cost round trips, not requests. A refusal is one more fast-slot call and
  nothing leaves; the forced fetch is one call and one GET. A lookup is now two to four model
  calls, one search and usually one page, so "1 search, 1 page read" is what the card says for a
  merchant with a site of its own.
- The confidence cap is visible: the card writes "unsure" instead of a percentage, and 0.6 is
  below the pipeline's 0.75, so a capped lookup is a Question card rather than a filed booking.
- The loop costs one fast-slot request per step, so a lookup is two to three model calls plus
  its searches. `LOOKUPS_PER_RUN` caps an import at five merchants; the rest are asked about in
  Question cards and looked up on the next run.
