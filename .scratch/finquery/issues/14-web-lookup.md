# 14: Self-directed web lookup

**What to build:** When web lookup is switched on in Settings, the categorizer and the chat agent can look up a merchant they do not recognize. Only a scrubbed merchant token leaves the machine. The agent runs a search loop of its own, deciding how many searches and page reads it needs within a budget, and stops when it has enough. Every request is written to the outbound log before it is sent and is visible in Settings. Results are cached per merchant token so a merchant leaves at most once per profile. Off by default.

**Blocked by:** 07 Categorization at import with Question card

**Status:** done

- [x] Merchant token scrubber removing amounts, dates, IBANs, card and reference numbers, personal names
- [x] Search through a keyless multi-backend library with explicit backend fallback and error handling on rate limits; page fetch with size and time limits
- [x] Self-directed loop with a search and fetch budget; the agent's stop decision is its own
- [x] Outbound log written before each request; Settings shows the switch and the log
- [x] `lookup_merchant` tool for the chat agent and a lookup stage in the categorizer when enabled
- [x] Sources rendered in the transcript with the AI Elements sources component
- [x] HTTP-seam tests with a stubbed search client: switch off means no outbound call, token scrubbing, cache hit avoids a second request, log entry precedes the request
- [x] Browser verification of an unknown merchant lookup

## Comments

Done 2026-09-04. 81 passed, 2 skipped (`tests/test_web_lookup.py` adds 12). Design recorded in
`docs/adr/0010-web-lookup-behind-a-merchant-token.md`. Screenshots: /tmp/finquery-14/.

`src/finquery/weblookup/` is the whole feature, five small modules:

- `scrub.py`: `scrub(description, counterparty)` starts from `merchants.merchant_of(...).key`
  and additionally drops amounts, dates (numeric and month names), IBANs, card, customer and
  reference numbers **with the label that introduces them** (`PERS.NR 4711`, `REF 8841`), and
  legal forms. A booking whose name reads as a person is refused whole: `MerchantToken("",
  reason)`, no partial token and no request. `safe_query` holds the query the model writes to
  the same rule before it is sent.
- `client.py`: `ddgs` 9.16 in a thread (`backend="duckduckgo,bing,brave"`, region de-de, five
  results, 5 s), `SearchUnavailable` for a rate limit (9.16 never raises `RatelimitException`,
  so the message is inspected for HTTP 429 or 403); a fetch is one `httpx` GET, 10 s, 300 kB
  cap, stdlib `HTMLParser` to text, at most one redirect and only to the same host. Both behind
  the `WebClient` protocol.
- `loop.py`: the decision agent (forced single tool `decide`) and `run_loop`. One step is one
  fast-slot request; our code executes it, appends the observation and asks again.
- `store.py`: the outbound log (`OutboundJournal.before` commits the row, `after` settles the
  status) and the per-token cache, both on their own short-lived sessions.
- `service.py`: `Lookups.merchant` (scrub, refuse or continue, cache, loop, keep) and
  `lookups_for`, the one place the switch is read: it returns `None` when web lookup is off, so
  "off" needs no branch in the callers.

**The loop's decision schema** (`decide`, one call per step):

    action        "search" | "fetch" | "finish"
    query         the web query, for a search
    url           one of the URLs it was shown, for a fetch
    summary       what the merchant is, for a finish
    category      one of the profile's categories, for a finish
    subcategory   one of that category's subcategories, or null
    confidence    0.0 to 1.0, required on every decision (0 for a search or a fetch)
    sources       the URLs it relied on, for a finish

Budget: `MAX_SEARCHES = 4`, `MAX_FETCHES = 3`, `MAX_STEPS = 10`. The model is told what is left
and stops itself; a kind whose budget is gone answers "refused: no searches left in the budget"
and the prompt says "You have no searches and no fetches left. Finish now." Our code also
refuses a URL that was not in its own results, so a fetch can only go where a logged search
pointed.

`confidence` is the one required field, and that was the one real fight. Every other field has
to be optional (a search has no summary), and with an optional float Gemma 4 26B simply left it
out or sent 0, which means a lookup can place nothing. Required plus "send 0 for a search"
matches the categorizer's proven shape and got 1.0, 1.0 and 0.9 on the three merchants in the
verification. A finish that still sends 0 is handed back once, then taken as it is.

Integration:

- `ChatDeps` gained one field, `web_client`, and `api/chat.py` one line. The tool
  `lookup_merchant` is declared through `prepare=_only_when_web_lookup_is_on`, which reads the
  profile's switch per run, so flipping it in Settings takes the tool away from the next turn.
  Two prompt paragraphs, both from the dynamic `web_lookup_brief` instruction next to
  `data_brief` (`WEB_LOOKUP_ON` names the budget and the privacy rule, `WEB_LOOKUP_OFF` says it
  is off and where to switch it on), so `SYSTEM_PROMPT` and its closing paragraphs are
  untouched.
- Categorizer: stage 2b in `pipeline.categorize_rows` between the dictionary and the model,
  `lookups: Lookups | None`. What it places at or above the threshold is placed; what it places
  below becomes the first button of a Question card exactly like a model guess; a merchant it
  answers never reaches the model. `LOOKUPS_PER_RUN = 5` per run, busiest first, and a refusal
  costs nothing so it does not use that budget. `Report` gained `by_lookup`, `lookups` and
  `lookups_refused`, `CategorizeOut` the same three, and the Import page line reports them.
- Endpoints: `GET /api/settings?profile_id=`, `PATCH /api/settings` (body `profile_id`,
  `web_lookup_enabled`), `GET /api/outbound-log?profile_id=&limit=`.
  `profile.web_lookup_enabled` is a new column with a `db.NEW_COLUMNS` entry;
  `outbound_request` and `web_lookup` are new tables.
- Frontend: `components/lookup-tool.tsx` (the tool step: token, "1 search", the suggested
  category with its confidence, the summary, and the AI Elements `sources` component, added
  with `npx shadcn@latest add .../sources.json`), `components/web-lookup-card.tsx` (the switch
  and the log on the Settings page, shadcn `switch`), `chat-view.tsx` renders
  `tool-lookup_merchant`, `lib/api.ts` has the tool types, `settingsQuery`, `patchSettings` and
  `outboundLogQuery`.

Tests: `tests/conftest.py` gained a `web_client` fixture that every module gets as `NoWeb`,
which **fails when it is called at all**, so no test can reach the network by accident;
`tests/test_web_lookup.py` overrides it with `StubWeb` (scripted hits and pages, a record of
every call, and a `watch` hook that snapshots `GET /api/outbound-log` at the moment a request
goes out, which is how "the log entry precedes the request" is asserted). The loop's model is
scripted through `decide` with stateless deciders (a function of the token and how many steps
have run), so four lookups in one turn can be answered in any order. Requests per turn are the
usual three plus one per loop step.

Watch out for two things:

- The person rule is exactly two capitalized words with no legal form and no business word
  (`BUSINESS_WORDS`, matched as the whole word or its ending so "Hausverwaltung" is a business
  and "Hoffmann" is not). It refuses on doubt: "ROFU Kinderland" was not looked up during
  verification, which costs a lookup and never a name. A lower-case person name in a booking
  text is not caught; a list of given names is the upgrade path, noted in the module.
- `weblookup` imports `categorize.merchants`, so `pipeline` imports `Lookups` under
  `TYPE_CHECKING` only. Importing it at runtime closes a circle and breaks
  `import finquery.weblookup` when that happens to come first.

Verified on OpenRouter on port 8081 with a throwaway database and the shipped year (433 rows,
Sparkasse preset). With the switch off: categorization was 384 by the dictionary, 24 by the
model, 25 Needs review, `lookups` 0, and the outbound log empty; asked what two merchants were,
the assistant answered "Die Websuche ist fuer dieses Profil deaktiviert ... in den
Einstellungen aktivieren" and made no call. Switched on in Settings, "Was ist KARLS DANKT auf
meinem Kontoauszug?" left exactly one request (`karls was ist Unternehmen`, token `karls`) and
came back with Karls Erlebnis-Dorf and four sources under the answer; asking again in another
conversation said "from the lookup cache of this profile, nothing left the machine" and added
no log entry. A three-merchant turn (Decathlon, Rossmann, HelloFresh) ran three loops of one
search each with confidences 1.0, 1.0 and 0.9. Nordsee is the one that used the loop for real:
two searches (`nordsee was ist`, then `Nordsee restaurant Fischgeschaeft`) before it finished.
A second small import with two unknown merchants gave `by_dictionary 1, by_lookup 2, by_model
0, needs_review 0, model_calls 0`: the lookup stage placed both rows (Douglas to Shopping,
Snipes to Shopping > Clothing) and the categorizer was not needed. **Typical searches per
lookup: one**, two when the first result set was thin. The outbound log after all of it is ten
rows, every one a search whose target carries nothing but a merchant token.

The one thing the browser could not do: the Import page's own report line. The sandbox refuses
`agent-browser eval` and `agent-browser upload` is off limits, so that line was verified
through the endpoint it renders (`POST /api/imports/{id}/categorize` returning the three new
counters) plus `tsc` and the build, not by dropping a file into the page.

Screenshots: `/tmp/finquery-14/01-settings-off.png` (switch off, empty log),
`03-outbound-log.png` (one entry after the first lookup), `04-cache-hit.png`,
`05-sources-open.png` (the sources component expanded), `06-lookup-off-answer.png`,
`08-outbound-log-full.png` (ten entries, tokens only), `09-three-lookups.png` (three lookups in
one turn with confidences), `10-transactions-placed.png` (a row the lookup stage filed).

Merged into main on 2026-09-04 on top of 01 to 07, 09, 12, 13, 16, 18 and 19. What
changed in the merge:

- `agent.py` is the union of eight tools on one `ChatDeps`: `query`, `chart`,
  `propose_changeset`, `apply_simple_edit`, `remember`, `set_rule`, `review_batch` and
  `lookup_merchant`, plus the `ask_user` toolset. `ChatDeps` is now the seven-field union, and
  **`web_client` had to go before `narrate`**: `narrate` carries a default and a dataclass
  cannot put a field without one after it. Only `api/chat.py` builds a `ChatDeps` and it passes
  every field by name, so nothing else had to move.
- `SYSTEM_PROMPT` is untouched by this ticket, as intended: both web-lookup paragraphs come
  from the dynamic `web_lookup_brief` instruction, which now sits next to `data_brief` and
  ticket 06's chart lines without either touching the other.
- `app.py`: `TransactionEditError` comes from `finquery.edits` (ticket 09 moved it out of
  `api.transactions`), so the branch's own import of it was dropped. `settings_api.router` is
  included next to `models_api`, `changesets` and the rest. Settings and the outbound log are
  one router, so there is nothing else to wire.
- `routes.tsx`: the Settings page renders `TaxonomyCard`, `ModelsCard` and `WebLookupCard` in
  `space-y-6` (main's spacing, which the taxonomy card was built for).
- `lib/api.ts` is the union of the tool map: `query`, `chart`, `ask_user`, `set_rule`,
  `review_batch`, `propose_changeset`, `apply_simple_edit`, `lookup_merchant`, with
  `ChangesetToolPart`, `ChartToolPart` and `LookupMerchantPart` next to each other.
  `chat-view.tsx` renders the lookup branch after the changeset and chart branches.
- **Beyond mechanical resolution:** the four tests that build their own app instead of using
  the `app` fixture (`test_chat.py`, `test_conversations.py`, `test_local_provider.py` twice)
  now pass `web_client=NoWeb()` too. Web lookup is off by default so they never reached the
  network, but they were constructing a real `HttpWebClient`, which made "no test can reach the
  network" true by accident rather than by construction.
- `uv run pytest` is 103 passed, 1 skipped (the local smoke test). `npx tsc --noEmit`,
  `npm run build` and `oxlint` are clean.
- Verified on OpenRouter on port 8077 with a throwaway database and the Sparkasse preset
  imported by REST: 433 rows, and `categorize` returned the union of both features' counters in
  one body (`by_rule 0, by_dictionary 384, by_lookup 0, by_model 24, needs_review 25,
  model_calls 1, lookups 0, lookups_refused 0`), the same figures as ticket 07 with the switch
  off. Settings showed all three cards (Categories, Models, Web lookup); switching Web lookup on
  and asking "Was ist KARLS DANKT auf meinem Kontoauszug?" left exactly one request (`karls was
  ist Unternehmen`, token `karls`), rendered the lookup step (token, "1 search", `Leisure >
  Events · 80%`, the summary) with "Used 2 sources" expanding to the two URLs, and the outbound
  log showed the one entry with its token and status. A chart ("monatliche Ausgaben 2025 als
  Diagramm") drew a line chart in the sandboxed frame with EUR axes and short month labels, and
  a changeset ("Move my Netflix bookings from July to December 2025 to Leisure") came back as a
  Recategorize card, applied, and the rows moved. Screenshots: /tmp/finquery-merge14/.
- Seen in verification, not caused by the merge: **"recategorize all Netflix rows" goes to
  `set_rule`, not `propose_changeset`**, on both slots. Both prompt blocks fit a
  merchant-shaped bulk recategorize ("`set_rule` ... immediately recategorizes every booking of
  that merchant" against "`propose_changeset` is for ... more than one row"), and the model
  picks the rule. A request the rule cannot express (a period, a subset) reliably proposes a
  changeset. If a card is wanted for the merchant case, the two blocks need one sentence saying
  which wins.
- Harness note: the server on this machine was SIGTERMed three times while a chat POST was
  streaming, once mid-turn. Launching it through a small script that calls `os.setsid()` first
  (macOS has no `setsid` binary) kept it alive for the rest of the verification.
