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
  whose name reads as a person (exactly two capitalized words, no legal form, no business word)
  is refused outright: there is no partial token, `scrub` returns nothing plus the reason, and no
  request is made. The query the model writes goes through the same rule (`safe_query`) before it
  is sent, because a query is also a trust boundary.
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
  never reaches the model. On the chat agent it is the `lookup_merchant` tool, declared only when
  the switch is on (its `prepare` reads the switch per run) and rendered with the AI Elements
  `sources` component.
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
- The person rule errs towards refusing: a two-word company with no business word in its name
  ("ROFU Kinderland") is not looked up. That costs a lookup and never a name. Widening it needs
  a list of given names, which is the noted upgrade path.
- The loop costs one fast-slot request per step, so a lookup is two to three model calls plus
  its searches. `LOOKUPS_PER_RUN` caps an import at five merchants; the rest are asked about in
  Question cards and looked up on the next run.
