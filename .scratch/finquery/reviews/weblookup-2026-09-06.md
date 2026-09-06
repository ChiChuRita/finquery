# Web lookup as a shared capability: review, prototypes, measurement

2026-09-06. A review of the web lookup elective as it stands (ADR 0010, explainer 15), a
prototype of a shared `WebKnowledge` helper under `.scratch/finquery/prototypes/weblookup/`,
and one measurement, all on OpenRouter with `google/gemini-3.8-flash` on the fast slot.
Nothing in `src/` was changed. Nothing private was sent: the synthetic year and public brand
names only. The exercise moved the OpenRouter credit meter 0.41 USD (4.55 to 4.14).

Question asked: can the lookup become a general capability every sub-agent can use, does it
help, and how do we make the most of it for the elective.

Short answer. As a capability: yes, small, with two callers beyond the chat tool (the
categorizer at import in batch, and the receipt path), and no for query, chart, memory and
statement extraction. Does it help: on this model, not measurably. The categorizer alone placed
96 percent of 72 unknown merchants correctly; with the lookup in front of it, 96 percent. The
gains are elsewhere: the person rule refuses 38 percent of a realistic unknown-merchant set
before any search happens, and the loop, on the hosted model, finished 34 of 82 lookups without
a single search and never fetched a page. Both are fixable in code and both matter more for the
elective than a new caller.

## 1. The current lookup, reviewed

What the code does (`src/finquery/weblookup/`): `scrub` derives a token from the merchant key,
`Lookups.merchant` checks the per-profile cache, then `run_loop` asks the fast slot for one
`decide` per step (search, fetch, finish) within 4 searches and 3 fetches, executes it, appends
the observation and asks again. Search is `ddgs` (duckduckgo, bing, brave; 5 hits, 240
character snippets); a fetch is one `httpx` GET (10 s, 300 kB, one same-host redirect) reduced
to text, 2,000 characters of which reach the next prompt. Every request is journaled before it is
sent; a result with a summary is cached per (profile, token).

### Findings

**F1. It finishes from memory, and it never read a page.** Of the 82 lookups that ran (steps 1
and 3), 34 finished with zero searches: "dm drogerie", "uber", "shell", "flixtrain", "temu"
answered from what the model already knew, at 0.95 to 0.99, with an empty `sources` list. The
prompt says "start with a search"; nothing in the code holds the model to it. Of the 48 that
searched, 46 searched once and 2 twice; none fetched a page. "Stop as soon as you know" is the
right product rule and the wrong elective rule: the sheet says "finds and visits pages and uses
the information within", and today that is true of the code and not of a run. Ticket 14 saw one
search per lookup on the local Gemma; the hosted model skips even that.

**F2. The person rule refuses the merchants that most need a lookup.** Of the 74 merchants in
the measurement set, today's `scrub` refused 28 (38 percent) as a person's name, and 24 of them
are companies: Sixt GmbH & Co Autovermietung KG, JET Tankstellen Deutschland GmbH, ERGO
Versicherung AG, Five Guys Germany GmbH, Conrad Electronic SE, Scalable Capital GmbH,
Physiotherapie Am Park, Metzgerei Huber. Two causes in `scrub.py`: `_capitalized_words` drops
the legal form (GmbH, AG, SE, KG) as uninformative before the words are counted, throwing away
the strongest business signal a booking carries (ADR 0010 says "two capitalized words with no
legal form"; the code counts after removing the form); and `BUSINESS_WORDS` is matched as a
whole word or suffix while several entries are stems that start a compound (`versicher`,
`metzger`), with `tankstelle`, `parfuemerie`, `fernsehen`, `mobility` missing. Case carries no
signal: a Sparkasse export prints "FIVE GUYS BERLIN" exactly like PayPal prints "ANNA WEBER".
The prototype's `widened_scrub` (a legal form anywhere means business, otherwise today's rule)
clears 21 of the 28 and still refuses the PayPal friends, Blumen Riedel, Physiotherapie Am Park,
VHS Berlin Mitte and Debeka (`a.G.`). The rest needs the module's own noted upgrade: a
given-name list.

**F3. A low-confidence lookup pre-empts a confident model.** In `pipeline.categorize_rows` a
merchant the lookup placed at any confidence leaves the model's batch; below the threshold it
becomes a Question card with the lookup's guess. Mustermann Systems GmbH (the synthetic
employer, "GEHALT ... PERS.NR 4711", money in) shows the cost: the lookup found nothing and
finished Shopping > Electronics at 0.20; the categorizer alone says Income > Salary at 0.90 from
the booking text. With the lookup on, the household is asked; with it off, the row is filed
correctly.

**F4. Bad tokens leave silently.** `E.ON Energie Deutschland GmbH` becomes `on energie`, `1&1
Telecom GmbH` becomes `telecom`, `Zeit Online GmbH` becomes `zeit`: `fold` splits on every
non-alphanumeric character and `_words` drops single characters and digit-only words. The hosted
model recovered all three; a local one will not, and the log then shows a token that is not the
merchant.

**F5. A failed search costs a search.** Two of 51 outbound requests failed with a connection
error from a backend (duckduckgo once, brave once); the loop charged each against the budget and
spent a model call on it. `ddgs` runs two engines at a time and raises the last exception when
its 5 s timeout passes empty, so the chain is less of a fallback than the ADR describes.

**F6. What is sound.** The journal-before-send contract, the URL allowlist, the same-host
redirect rule, "no conclusion is not cached", `safe_query` on the model's own query, the
forced-tool schema with `reasoning` first and a required `confidence`, and the tests (14 at the
HTTP seam, `NoWeb` everywhere else). Confidence is honest where it matters: Mustermann Systems
0.20, Schlöcker 0.30, and under today's rule not one wrong placement at or above the threshold.

**F7. Where it is used.** `agent.py:lookup_merchant` and the categorizer's stage 2b
(`pipeline._look_up`, five busiest unknown merchants per run). The receipt path does not use it:
an unmatched receipt becomes a draft whose description is the printed header ("Combi. Frisch.
Nebenan.") with no category, and the split legs are categorized from item text alone. Memory,
query, chart and extraction never touch it.

### Run log summary (step 1)

Twenty-one booking strings from `fixtures/synthetic/sparkasse-2025.csv` through today's loop
unchanged (`run_lookups.py`; every request in `results/review-lookups.json`).

| merchant | token | steps | queries | conclusion | conf | s |
| --- | --- | --- | --- | --- | ---: | ---: |
| LIDL Vertriebs GmbH | `lidl` | 1 search | what is lidl | Groceries > Supermarket | 0.99 | 4.5 |
| dm drogerie markt | `dm drogerie` | none | | Groceries > Drugstore | 0.99 | 1.9 |
| NETTO MARKEN-DISCOUNT | `netto marken discount` | none | | Groceries > Supermarket | 0.99 | 1.7 |
| Lieferando.de | `lieferando` | 1 search | lieferando | Dining > Delivery | 0.95 | 4.0 |
| DEAN AND DAVID | `dean david` | 1 search | dean david restaurant | Dining > Takeaway | 0.90 | 5.4 |
| Döner Haus Kreuzberg | `doener haus kreuzberg` | none | | Dining > Takeaway | 0.95 | 1.7 |
| Cafe Milchbart | `cafe milchbart` | 1 search | cafe milchbart | Dining > Cafe | 0.95 | 4.0 |
| VAPIANO Berlin Mitte | `vapiano mitte` | 1 search | vapiano mitte | Dining > Restaurant | 0.95 | 4.7 |
| UBER BV | `uber` | none | | Transport > Ride hailing | 0.95 | 2.0 |
| SHELL DEUTSCHLAND | `shell` | none | | Transport > Fuel | 0.95 | 1.9 |
| Telekom Deutschland GmbH | `telekom` | 1 search | telekom deutschland | Communication > Mobile | 0.95 | 4.1 |
| ADOBE SYSTEMS SOFTWARE | `adobe systems software` | 1 search | adobe systems software | Subscriptions > Software | 0.95 | 4.4 |
| BVG Berliner Verkehrsbetriebe | `bvg berliner verkehrsbetriebe` | none | | Transport > Public transport | 0.99 | 1.8 |
| Vattenfall Europe Sales GmbH | `vattenfall sales` | 1 search | vattenfall sales | Housing > Electricity | 0.95 | 4.8 |
| Allianz Versicherungs-AG | `allianz versicherungs` | none | | Insurance | 0.95 | 1.8 |
| Sparkasse Geldautomat | `sparkasse geldautomat` | none | | Cash > Cash withdrawal | 0.99 | 1.5 |
| Hausverwaltung Bergmann GmbH | `hausverwaltung bergmann` | 1 search | hausverwaltung bergmann | Housing > Rent | 0.95 | 4.2 |
| Mustermann Systems GmbH | `mustermann systems` | 2 searches | mustermann systems; "mustermann systems" gmbh unternehmen | Shopping > Electronics | 0.20 | 6.8 |
| Zahnarztpraxis Dr. Lorenz | `zahnarztpraxis dr lorenz` | 1 search | zahnarztpraxis dr lorenz | Health > Doctor | 0.95 | 5.0 |
| Apotheke am Markt | `apotheke` | none | | Health > Pharmacy | 0.99 | 2.4 |
| PayPal (ANNA WEBER) | refused | | | | | |

20 lookups ran, 9 with no search, 0 fetched a page, mean 3.4 s, 32 model requests (48k tokens
in, 4k out, 0.05 USD). All 12 outbound requests carried a merchant token and nothing else.
Every conclusion matched the generator's category except Mustermann Systems, where the low
confidence is the right answer.

## 2. Where web knowledge helps, and where it does not

The two rules that bound every row: nothing from a booking except a scrubbed merchant token may
leave, and no figure ever comes from the web.

| Sub-agent | The question the web would answer | Allowed? | Measured or expected gain | Verdict |
| --- | --- | --- | --- | --- |
| Categorizer at import (`categorize/pipeline.py`) | What does this unknown merchant sell, so it is filed without a Question card | Yes, the token only; already stage 2b | None on Gemini 3.8 Flash (96 to 96 percent); expected on a local 4B model that does not know Combi or Vogtlandbahn, unmeasured | Keep; fix F2 and F3 first, then batch |
| Receipt reader (`extract/bill.py`) | Which store or chain is this printed header, so the draft has a title and category and the legs have the store type as context | The header yes (a store name is not personal), the line items never (a basket is) | 4 of 7 non-dictionary headers resolved, 1 honest low, 3 refused by F2 | Build as the second caller, dictionary first |
| Statement reader (`extract/statement.py`) | Which bank layout is this | No need: recognized from the printed header in code (`layouts.py`); a page carries balances and names that may not leave | none | Do not |
| Query sub-agent (`query/subagent.py`) | Nothing: it writes SQL over the user's own rows | The numbers invariant forbids a figure from the web | none | Do not |
| Chart sub-agent (`chart/subagent.py`) | Nothing: it plans and codes a chart over query rows | Same | none | Do not |
| Memory distillation (`memory.py`) | Nothing durable: a memory is what the user said | Not forbidden, but a web fact already has a home, the lookup cache | none | Do not; the cache is "what this profile learned about merchants" |
| Chat agent (`agent.py:lookup_merchant`) | What is X on my statement | Yes, as today | Built; the gain is the evidence on the card (section 4) | Keep, improve the card |
| CSV mapping (`ingest/mapping_agent.py`) | Which bank prints this header | Column names are not personal, but six presets exist and an unknown header is one model call | tiny | Do not |

Honest note on the first row: the hosted fast model knows German chains, sometimes better than a
one-search snippet (Douglas: model Shopping, lookup Groceries > Drugstore). On the local tier
the model alone was 92 percent and the lookup did not improve it. The web will matter on the
local provider, where the fast slot is a 4B model; that is the measurement to run next, on the
same 72 merchants with `FINQUERY_PROVIDER=local`.

## 3. The prototype and its measurement

Files under `.scratch/finquery/prototypes/weblookup/`: `web_knowledge.py` is the
`WebKnowledge` helper (`about_one`, `about_many`: scrub, deduplicate by token, answer refused
and cached tokens without a request, run the rest sequentially with a one-second pause;
`resolve_store(header)`), one result shape `Knowledge` (summary, category, confidence, sources,
the queries and URLs it took, seconds, cached, refused-with-reason), reusing `scrub`, `run_loop`
and `HttpWebClient` unchanged, plus `widened_scrub` from F2. `common.py` is the metered model,
an in-memory journal and a recording client; `merchants.py` the sets with their hand-assigned
truth (acceptable categories, the expected subcategory where one is clearly right, a tier
`chain` or `local`); `results/` the tables, the JSON logs with every request that left, and the
shared cache.

### 3a. The categorizer with and without web knowledge

The synthetic year alone is too small (35 of its 39 merchants are dictionary hits), so the set
was grown with 69 public merchants outside `merchants.DICTIONARY`; two of the 74 were dictionary
hits after all (Zahnarztpraxis via `zahnarzt`, Shop Apotheke via `apotheke`), leaving 72: 48
chain, 24 local.

Arms, all on Gemini 3.8 Flash with the production prompts and the pipeline's 0.75 threshold:

- **A, model only**: the categorizer sub-agent as with the switch off. 3 calls.
- **B, lookup then model**: today's stage 2b. The lookup's category where it placed one (below
  the threshold it stays the lookup's and becomes a Question card, as in the pipeline), the
  categorizer for the rest.
- **B2**: as B with `widened_scrub`.
- **C, model with a brief**: the categorizer only, every entry carrying the lookup's one-line
  summary under the booking text: the "shared knowledge feeds the sub-agent" shape.

"Placed" is a valid category at or above the threshold; "correct" is the category in the truth
set; the subcategory is scored only where the truth names one.

| arm | n | placed | placed and correct | placed and wrong | correct at any confidence | subcategory right |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A model only | 72 | 70 (97%) | 69 (96%) | 1 | 71 (99%) | 54/56 (96%) |
| A, chain | 48 | 48 (100%) | 47 (98%) | 1 | 47 (98%) | 35/37 |
| A, local | 24 | 22 (92%) | 22 (92%) | 0 | 24 (100%) | 19/19 |
| B lookup then model | 72 | 69 (96%) | 69 (96%) | 0 | 71 (99%) | 54/56 (96%) |
| B, chain | 48 | 48 (100%) | 48 (100%) | 0 | 48 (100%) | 36/37 |
| B, local | 24 | 21 (88%) | 21 (88%) | 0 | 23 (96%) | 18/19 |
| B2 lookup (legal-form rule) then model | 72 | 69 (96%) | 68 (94%) | 1 | 70 (97%) | 54/56 (96%) |
| B2, chain | 48 | 48 (100%) | 47 (98%) | 1 | 47 (98%) | 36/37 |
| B2, local | 24 | 21 (88%) | 21 (88%) | 0 | 23 (96%) | 18/19 |
| C model with brief | 72 | 70 (97%) | 68 (94%) | 2 | 70 (97%) | 55/56 (98%) |
| C, chain | 48 | 48 (100%) | 46 (96%) | 2 | 46 (96%) | 36/37 |
| C, local | 24 | 22 (92%) | 22 (92%) | 0 | 24 (100%) | 19/19 |
| lookup alone, today's rule | 72 | 43 (60%) | 43 (60%) | 0 | 43 (60%) | 34/35 (97%) |
| lookup alone, legal-form rule | 72 | 64 (89%) | 63 (88%) | 1 | 63 (88%) | 49/51 (96%) |

The misses: A filed Fressnapf as Leisure > Hobbies at 0.90 and asked about the PayPal friend at
0.40 (correct behaviour). B had no wrong placement but sent Mustermann Systems to a card at 0.20
instead of Income > Salary (F3); of the 44 merchants the lookup placed, all 44 matched the
truth. B2 filed Parfuemerie Douglas as Groceries > Drugstore at 0.95 from a search (counted
wrong). C followed the lookup on Douglas and did not fix Fressnapf.

Cost: the 62 lookups that ran took 3.6 s each on average, 25 without a search, 0 with a fetch,
1.6 model calls each; 100 lookup calls against 3 categorizer calls for the same 72 merchants,
0.21 USD for the whole run. Placement rate and correctness: no gain on this model. The lookup's
own answers are as accurate as the model's (63 of 64 placed right) and better calibrated (0.20
and 0.30 where it did not know), which makes it a good source of evidence and a poor replacement
for the categorizer.

### 3b. Resolving a receipt header

Sixteen headers (`resolve_receipts.py`): the dictionary first, then `resolve_store`.

| header | dictionary | web | steps | conf |
| --- | --- | --- | --- | ---: |
| Combi. Frisch. Nebenan. | no | Groceries > Supermarket, "German supermarket chain in northwestern Germany" | 1 search | 0.95 |
| HIT-Tankstelle | no | refused (person rule) | | |
| Saurüsselalm | no | Dining > Restaurant, "Alpine pasture restaurant in Bad Wiessee" | 1 search | 0.95 |
| NEUHAUSER AUGUSTINER | no | refused (person rule) | | |
| Fressnapf Köln-Ehrenfeld | no | refused (person rule) | | |
| SCHLÖCKER | no | Groceries > Drugstore, "likely a typo for Schlecker" | 4 searches | 0.30 |
| VOGTLANDBAHN-GMBH | no | Transport > Public transport, "regional railway operated by Die Länderbahn" | 3 searches | 0.95 |
| Kreiller Str. 81673 München | no | refused (right, for the wrong reason: it is an address) | | |
| HANS IM GLUECK Burgergrill | only on the pipeline's second try (`hans glueck burgergrill` misses the pattern `hans im glueck`) | Dining > Restaurant | 1 search | 0.95 |
| Ecenter EDEKA, ALDI HESEL, ROSSMANN (2), Esso Station, EDEKA Sander, OBI Baumarkt | hit | not needed | | |

Nine of sixteen never need the web. Of the seven that do, four resolve with a usable title and
category, one is an honest low on a misread header, three are refused by F2 (HIT-Tankstelle and
Fressnapf are plainly businesses). 15 model calls, 0.03 USD. The gain in the product: the draft
card reads "Combi, supermarket, Groceries" instead of "Combi. Frisch. Nebenan." with no
category, and the legs of a split get "a supermarket receipt" as one line of context. Small,
visible, and a good second demo beat.

## 4. Making the most of the elective

The sheet asks for repeated, self-controlled, and further than the direct results (find and
visit a page, use what is on it). The loop is repeated and self-controlled in code. The third is
where the code and the demo should move, and most of it is cheap.

Cheap (prompt and a few lines of code, about a day together with F2):

1. **At least one search, in code.** A finish before any search is refused once, the same shape
   as the confidence-0 nudge. Without it a lookup on the hosted model is a knowledge recall with
   a Wikipedia-shaped summary and no sources.
2. **One fetch when a hit is the merchant's own site or Wikipedia.** Add to `RULES`: when a
   hit's host contains the token, or is a Wikipedia article about it, fetch it before finishing
   and quote one sentence. One more model call and one GET; the card then reads "1 search, 1
   page read". Today no run does this unprompted.
3. **An `evidence` field on `decide`.** A verbatim sentence from a snippet or page, checked in
   code to occur in the observations (the verbatim guard idea from extraction), shown under the
   summary with its source. Confidence with a quote is what a grader can check.
4. **A second query when the token is one word or generic** (`zeit`, `action`, `telecom`): add
   "Unternehmen" or the counterparty's second word. One sentence in the prompt.
5. **Retry a failed search once without charging the budget** (F5).
6. **Fix the person rule** (F2) and let a below-threshold lookup fall through to the model with
   its summary as context (F3). No model call; the largest gain in this report.
7. **The card and the log as proof.** Open the log next to the card in the demo and read one
   row: kind, target, token, status. The card gains the quote and the fetched URL.

Expensive (a ticket of its own, only if the grade needs it): 8. an Impressum or About page as a
second hop (one fetch of a same-host link found in the fetched HTML, so still a URL it was
shown; needs link extraction in `html_to_text`); 9. two lookups at a time for imports of an
unknown bank (five sequential per run is right for the demo, sixty unknown merchants would take
twelve runs).

The demo, three minutes: switch on, empty log; a merchant the dictionary does not know and the
model should not simply recall ("Combi Verbrauchermarkt", or "Saurüsselalm" from a receipt); the
card with the token that left, "1 search, 1 page read", the quoted sentence and its source; the
log with the two rows; the same merchant in a second chat from the cache, no new row; the Combi
receipt dropped in, its draft titled "Combi, supermarket". Keep "Hausverwaltung Bergmann" out:
the loop finds a real property manager of that name and is 0.95 sure about the wrong one.

## 5. Recommendation

Build it as a shared capability: yes, but small. `WebKnowledge` is a thin layer over the
existing module: `about_many` for a batch, `resolve_store` for a header, the existing
`Lookups.merchant` for the chat tool, one cache, one journal, one switch.

The three uses, in order of value: (1) the chat tool as today, made convincing for the elective
by items 1 to 3 and 7; (2) the categorizer at import, already wired, made useful by F2 and F3
and a batch entry point; (3) the receipt draft and legs, one new call site. Not query, chart,
memory, statement extraction or mapping.

Ticket-sized scope for an Opus implementation agent (one ticket, about a day):

- `weblookup/scrub.py`: a legal form anywhere in the counterparty (including `e.V.`, `a.G.`,
  `eG`, `B.V.`) short-circuits to business before the word count; `BUSINESS_WORDS` stems
  matched at the start of a word for `versicher`, `metzger`, `physio`, `tankstell`, `parfuem`,
  `einrichtung`, `fernseh`, `mobility`, `capital`, `entertainment`; a list of the two hundred
  most common German given names that refuses a name with one of them in either position
  ("Anna Weber", "ANNA WEBER", "Weber Anna") and passes "Metzgerei Huber". Tests for every name
  in F2 in `tests/test_web_lookup.py`.
- `weblookup/loop.py`: a finish with no search is refused once; `evidence` on `Decision`,
  checked verbatim against the observations; the fetch rule for an own-site or Wikipedia hit; a
  failed search retried once without charging the budget; `Outcome.evidence` and the fetched
  URLs through `Lookup.payload` to the card.
- `weblookup/service.py`: `Lookups.merchants(pairs)` (deduplicate by token, cache, sequential
  with a one-second pause) used by `pipeline._look_up`; `Lookups.store(header)` used by
  `extract/bill.py:bill_outcome` for the draft's title and category (dictionary on both tries
  first, the web second, only with the switch on) and passed to `group_items` as one line of
  context.
- `categorize/pipeline.py`: a lookup below the threshold no longer removes the merchant from
  the model batch; its summary rides along as a `web:` line on the entry (arm C's shape).
- Frontend `lookup-tool.tsx`: the evidence quote with its source; "1 page read" made a link.
- Docs: ADR 0010 consequences (the person rule, the one-search floor), explainer 15 (this
  report's figures replace "typical searches per lookup: one"), demo script step 27.

Do not build now: the Impressum hop, parallel lookups, a knob for `LOOKUPS_PER_RUN`. Do run
next, before the video: the same 72 merchants on `FINQUERY_PROVIDER=local`, arms A and B.

## 6. Risks

- **Privacy must not regress.** Widening the person rule is the whole gain and the whole risk.
  Keep the order: legal form wins, then the given-name list refuses, then the two-word count.
  A wrong widening leaks a name into a search engine's logs; a wrong narrowing costs a lookup.
- **Confident about the wrong merchant.** A local token ("hausverwaltung bergmann", "metzgerei
  huber") matches many real businesses; the loop returns one at 0.95 and the pipeline files
  anything at or above 0.75. Cap the confidence when no source's title or host carries the
  token; the evidence quote makes the wrong one visible at least.
- **The loop is only as web-bound as the code makes it.** A stronger hosted model recalls
  instead of searching; the one-search floor and the fetch rule have to be code, not prompt, or
  the elective claim depends on which model is running.
- **Search backends.** ddgs is keyless and unofficial; two of 51 requests failed here. Warm the
  cache on the demo merchants beforehand (a second run of `run_lookups.py` does that).
- **Cost and time.** Hosted, 2 to 3 fast-slot calls and 2 to 12 s per lookup; locally the demo
  script measured 53 s. One fetch more adds one call and up to 10 s. Five per import run stays.
- **A receipt header is not a booking.** It can be an address ("Kreiller Str. 81673 München").
  Resolve only a header the reader returned as a merchant name, and never the items.
- **The elective wording will still be partly true.** A well-known chain is answered after one
  search and one page, and that is correct. Say so in the talk: the budget is a ceiling, the
  model stops when it knows, and here is the one that took three searches (Vogtlandbahn) and
  the one that gave up honestly (Schlöcker).
