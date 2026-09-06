# 53: Web lookup as a shared capability, and a loop that really visits pages

**What to build:** Section 5 of `.scratch/finquery/reviews/weblookup-2026-09-06.md`, accepted by the user on 2026-09-06. The existing web lookup module becomes a thin shared capability with three callers (the chat tool, the categorizer at import in a batch, the receipt header), its person rule stops refusing companies, and the loop is held in code to at least one search, one page read when a hit is the merchant's own site or Wikipedia, and a verbatim evidence quote the card shows. No new caller for query, chart, memory, statement extraction or CSV mapping.

**Blocked by:** 14, 21, 22, 42 (merged)

**Status:** done

Decisions, settled (the review's findings F1 to F7 are the evidence):
- `weblookup/scrub.py`: a legal form anywhere in the counterparty (GmbH, AG, SE, KG, KGaA, UG, e.V., a.G., eG, B.V., Ltd, Inc, S.A., OHG, GbR, mbH, and the "& Co" forms) short-circuits to business before the word count. `BUSINESS_WORDS` stems match at the start of a word for `versicher`, `metzger`, `physio`, `tankstell`, `parfuem`, `einrichtung`, `fernseh`, `mobility`, `capital`, `entertainment`, and the missing `tankstelle`, `parfuemerie`, `fernsehen`, `mobility` are added. A list of the two hundred most common German given names (in the module, plain data) refuses a name with one of them in either position ("Anna Weber", "ANNA WEBER", "Weber Anna") and passes "Metzgerei Huber". Order: legal form wins, then the given-name list refuses, then today's two-word rule. Tokens keep meaningful short parts: `E.ON` stays `eon`, `1&1` stays `1und1` or `1&1`, `Zeit Online` keeps `online`. Tests for every name in F2 and F4 of the review, both directions.
- `weblookup/loop.py`: a finish with no search is refused once (the same shape as the confidence-0 nudge); `evidence` on `Decision`, a verbatim sentence that must occur in the observations (checked in code, otherwise the finish is refused once with the reason); a fetch rule: when a hit's host contains the token, or is a Wikipedia article about it, the loop fetches it before finishing (in code, a forced fetch step, not a prompt line); a failed search backend is retried once without charging the budget; a second query is suggested in the prompt when the token is one word or generic; confidence is capped at 0.6 when no source's title or host carries the token. `Outcome.evidence`, the fetched URLs and the counts reach the card through `Lookup.payload`.
- `weblookup/service.py`: `Lookups.merchants(pairs)` deduplicates by token, answers refused and cached tokens without a request, runs the rest sequentially with a one-second pause, journals as today; `Lookups.store(header)` for a receipt header (dictionary on both tries first, the web second, only with the switch on). One cache, one journal, one switch.
- `categorize/pipeline.py`: stage 2b uses `Lookups.merchants`; a lookup below the threshold no longer removes the merchant from the model batch, its summary rides along as a `web:` line on the entry (arm C of the review). `extract/bill.py`: the draft's title and category from `Lookups.store` when the header is not in the dictionary, and one line of store context handed to `group_items`; never the items.
- Frontend `lookup-tool.tsx` (or wherever the web lookup card lives): the evidence quote with its source, "1 search, 1 page read" with the page as a link, the confidence cap visible as "unsure" wording.
- Docs: ADR 0010 consequences (the person rule order, the one-search floor, the fetch rule), `docs/explainers/15-elective-web-search.md` (the review's figures replace "typical searches per lookup: one"; the demo merchants), `docs/demo-script.md` step 27 (Combi or a receipt from Saurüsselalm; keep Hausverwaltung Bergmann out), CONTEXT.md if a term is new.
- Not built: the Impressum second hop, parallel lookups, a knob for lookups per run.
- Privacy must not regress: nothing but the scrubbed token leaves; the journal-before-send contract, the URL allowlist and the same-host redirect rule stay; the tests that assert them stay green.

- [x] Scrub: legal form rule, stems, given-name list, token fixes; tests for every F2 and F4 example
- [x] Loop: one-search floor, evidence verbatim check, own-site or Wikipedia fetch rule, failed-search retry, confidence cap, payload fields; tests with the scripted FunctionModel and a fake web client for each rule
- [x] Service: `merchants` batch and `store`; pipeline and bill callers; a below-threshold lookup rides along as context; tests at the HTTP seam (an import with unknown merchants runs one lookup per distinct token; a receipt draft gets a title and category from a header the dictionary does not know; the switch off means no request)
- [x] Card: evidence quote, source, page link, unsure wording; both themes
- [x] Docs and demo step; `uv run pytest` green, `npm run build` clean; a rerun of the review's `run_lookups.py` and `resolve_receipts.py` on the new code with the tables in Comments (searches per lookup, pages read, refusals), credit permitting; headful browser verification (named session, own port above 8100, throwaway database, Gemini 3.8 Flash, few turns): the switch on, a lookup of a merchant the model cannot recall showing the token, "1 search, 1 page read", the quote and the log rows; the same merchant from the cache in a second chat; a receipt draft with a resolved store; screenshots in `/tmp/finquery-53/`

## Comments

**2026-09-06, implementation agent.** Done on branch `worktree-agent-abb18933e9693c28d`, six
commits. The reruns and the browser check ran on `qwen/qwen3.5-9b` on both slots, not on Gemini:
the model class the local provider ships, per the amended CLAUDE.md. The review's own figures
were measured on Gemini 3.8 Flash, so the before and after columns below are two models as well
as two versions of the code. The credit meter moved 0.18 USD (3.91 to 3.73) for both reruns and
the browser session together.

### What changed, by file

`weblookup/scrub.py`: `has_legal_form` reads the printed string with abbreviations squashed
(`e.V.` to `ev`, `a.G.` to `ag`, `S.a.r.l.` to `sarl`) plus the `& Co` forms, and it short-circuits
to business before the words are counted. `BUSINESS_STEMS` matches a trade at the start of a
compound; `tankstelle`, `parfuemerie`, `fernsehen` and `mobility` join `BUSINESS_WORDS`.
`GIVEN_NAMES` is two hundred folded German given names and refuses either position of a two-word
name, before the business-word exemption. All three read `_name_source`, the same string the rule
always read, so a PayPal counterparty's legal form can never vouch for the friend in the booking
text (its own test). `_NUMBERISH` is now two adjacent digits rather than any digit, and
`_normalized` unglues `E.ON` and `1&1`, so the F4 tokens are `eon energie`, `1und1 telecom` and
`zeit online`.

`weblookup/loop.py`: `evidence` on `Decision`; `quoted_verbatim`, `own_page`, `names_the_token`,
`from_the_web` as pure functions; the four rules in `run_loop`, each refused once per lookup; the
free retry of a failed search inside the same step; `Outcome.evidence`, `evidence_url`, `pages`,
`capped`. `MAX_STEPS` is 11.

`weblookup/service.py`: `Lookups.merchants(pairs, taxonomy, limit=)` and `Lookups.store(header)`,
`Lookup.brief` and the new payload fields. `weblookup/store.py` and `db.py` keep the quote, the
pages and the cap with the cached row (four additive columns in `NEW_COLUMNS`).

`categorize/pipeline.py`: `_look_up` returns guesses **and** briefs; only a lookup at or above
0.75 skips the model, the rest ride along. `categorize/subagent.py`: `MerchantBatchEntry.web`
and one rule line telling the model it is a hint. `extract/bill.py`: `Store`, `known_store`
(both dictionary tries), `resolve_store`, the draft's title, the `store` block on the payload,
one line of shop context for `group_items`. `agent.py` and `ingest/chat_import.py` thread
`lookups` to the receipt path. `frontend/src/components/lookup-tool.tsx` and `lib/api.ts`: the
quote with its host, "1 page read" as a link, "unsure" instead of a percentage when capped.

### Rerun 1: the twenty synthetic booking strings (`run_lookups.py`)

| | review, Gemini 3.8 Flash, old code | ticket 53, Qwen3.5 9B, new code |
| --- | ---: | ---: |
| lookups that ran | 20 | 20 |
| finished with no search at all | 9 | **0** |
| searches per lookup, mean | 0.65 | **1.7** |
| lookups that read a page | 0 | **12** |
| pages read | 0 | 12 |
| finishes with a quote from a page or a snippet | n/a | 12 |
| confidences capped at 0.6 | n/a | 6 |
| refusals before anything left | 1 (PayPal/Anna Weber) | 1 (same) |
| at or above the pipeline's 0.75 | 20 | 12 |

The full table is `.scratch/finquery/prototypes/weblookup/results-53/review-lookups.md`. The
drop from 20 to 12 placeable answers is the cap doing its job on Qwen: `uber`, `shell`,
`hausverwaltung bergmann`, `mustermann systems`, `adobe systems software` and
`bvg berliner verkehrsbetriebe` came back with sources that never named the merchant, so they go
to a Question card instead of being filed. `hausverwaltung bergmann` is exactly the risk the
review's section 6 named, and it is now visible on the card rather than a confident wrong filing.

### Rerun 2: the sixteen receipt headers (`resolve_receipts.py`)

| | review, Gemini | ticket 53, Qwen |
| --- | ---: | ---: |
| headers the dictionary places | 9 | 8 (Hans im Glueck moved to the web here; in the app `known_store` makes both tries and places it) |
| headers refused by the person rule | 4 | **3** |
| resolved with a title and a category | 4 | **5** |
| honest low or no conclusion | 1 | 1 (`SCHLÖCKER`, 0.00 after four searches) |

`HIT-Tankstelle` is the one the widened rule bought: a business the old rule refused, now
`hit tankstelle`, Transport > Fuel at an honest 0.30. `NEUHAUSER AUGUSTINER` and
`Fressnapf Köln-Ehrenfeld` are still refused (two capitalized words once the city is stripped,
no legal form, no trade word), and `Kreiller Str. 81673 München` is still refused, correctly.
Table: `results-53/resolve-receipts.md`.

### One bug the rerun found

`adobe systems software` came home quoting "None found as search failed." and
`hausverwaltung bergmann` quoted its own reasoning. Both passed the verbatim check because a
refused step carries the model's reasoning back to it and a failed search carries the backend's
message, so the loop had written both into the prompt itself. Fixed in `from_the_web`: only hits
and page text are evidence. Commit "a quote may not come out of what the loop itself wrote", with
a unit test.

### Browser verification

Headful, session `ticket53`, port 8151, throwaway database, Qwen3.5 9B on both slots. Nine
screenshots in `/tmp/finquery-53/`, both themes.

- Switch on, log empty; then "Was ist VOGTLANDBAHN-GMBH auf meinem Kontoauszug?": the card reads
  token `vogtlandbahn`, "1 search, **1 page read**" with the page as a link, the quote *"Die
  vogtlandbahn ist eine Länderbahn, die im Vogtland und darüber hinaus verkehrt."* over
  `de.wikipedia.org`, Transport > Public transport 95 percent, "Used 2 sources". The loop fetched
  the Wikipedia article itself: the model only ever searched and finished.
- The outbound log lists six rows, each carrying nothing but a merchant token, including the two
  `ok` rows of that lookup and, from an earlier attempt, two identical `Combi Verbrauchermarkt
  was ist` rows 0.4 s apart, which is the free retry of a failed backend in production.
- The same merchant in a second chat: "from the lookup cache of this profile, nothing left the
  machine", with the quote and the sources kept, and no new log row.
- The Hans im Glueck receipt through the composer's API path: the draft card reads "Hans im
  Glueck" with "HANS IM GLUECK Burgergrill · Cash" under it and Dining > Restaurant from the
  store block, where it used to read the printed header with no category.

### What is left, and two honest notes

- **Asked in plain German, Qwen answers a repeated merchant from its memory rather than calling
  the tool a second time.** The prompt asks for the second call precisely so the cache card is
  the user's proof; the hosted 9B model does not always obey, and the card above needed the tool
  named. Worth a line in the talk, and a prompt experiment rather than code.
- The suite went from 348 to 391 tests. `ddgs` answered "No results found" for several minutes
  while the two reruns were hammering it, which is what the first browser attempt hit: warm the
  demo merchants beforehand, as the review's risk section says.
- Not built, on purpose: the Impressum second hop, parallel lookups, a knob for
  `LOOKUPS_PER_RUN`. The next measurement the review asks for (the same 72 merchants on
  `FINQUERY_PROVIDER=local`, arms A and B) is still open.
