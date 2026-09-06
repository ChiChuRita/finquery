# FinQuery domain glossary

The words the code, the tickets and the UI use. One meaning per term. Where a synonym is
tempting, it is listed as avoided so the vocabulary stays stable.

## Data

**Profile**: the isolation boundary. Every account, transaction, category, rule, memory,
conversation and preference record belongs to exactly one profile. A default profile is created
at startup. Avoid: user, workspace, account (an account is a bank account, see below).

**Onboarding**: the three steps and the finish a profile opens with the first time: which
categories it uses, how the assistant should answer, and its first file. Its state is on the
profile, `not_started`, `done` or `skipped`. A profile that has not started it opens onboarding
instead of an empty chat, once, and Settings reopens it. Avoid: wizard, tour, setup flow.

**Answer language**: the language the assistant writes its answers in, one per profile: follow
(the language of each message, the default), German or English. A fixed choice overrides the
follow-the-message rule in the prompt. On follow, the language of the newest message is
detected in code from its function words and named in the prompt, because the local fast model
left to detect it answers German data in German. Avoid: locale, UI language (the interface is
English either way).

**Account**: a bank account or card, derived from imports or created manually. Avoid: profile,
wallet.

**Transaction**: one booking with exactly one amount, a description, a date, an account, an
optional category and subcategory, an enrichment, a source (import id, manual, bill photo) and
a fingerprint for duplicate detection. Avoid: booking, entry, payment, row (row is the table
view of a transaction, not the concept).

**Split**: a transaction that is a parent with children. Children reference the parent and must
sum to its amount. Queries and charts count only the children of a split parent, never the
parent. Avoid: itemization, breakdown.

**Category** and **Subcategory**: the profile-scoped taxonomy, one level deep. About fifteen
defaults are seeded per profile. Avoid: tag, label, bucket.

**Needs review**: the state of a transaction with no category. It is an absence, not a
category. Avoid: uncategorized, pending.

**Unknown**: a real category a human assigns when a transaction fits nothing. Automation never
produces it. Avoid: other, misc.

**Category rule**: a profile-owned pattern to category mapping created from Question card
answers, chat statements or manual edits. It is the highest-priority categorization stage.
Avoid: filter, mapping.

**Enrichment**: the friendly title and short description attached to a transaction (Edeka
Filiale 1234 becomes Edeka, supermarket). Avoid: normalization, cleaning.

**Import**: a record of one ingestion: file name, kind, mapping used, row counts, duplicates
found and what was decided about them, reconciliation result. Avoid: upload, sync.

**Duplicate candidate**: a booking an ingestion did not insert because the profile may already
have it, either exactly (same account, date, amount and normalized description) or nearly (same
amount, at most two days apart, a similar description). It is not a transaction and it is not
lost: the user answers **Keep both** (insert it) or **Remove** (leave the data as it is), on a
Question card in the chat, and the decision stays on the candidate. Avoid: duplicate
(what is a duplicate is the user's call, not ours), conflict, collision.

**Extraction**: what the extraction sub-agent read out of one PDF or photo, before anything is
written: the rows with the span each figure was read from, the flags the guards left on them and
the reconciliation. Stored on the attachment until the review is answered, so the rows that are
committed are the rows the user was shown. Avoid: parse, OCR (there is no OCR; a page with no
text layer is looked at by the vision path).

**Verbatim guard**: the rule that an amount, a balance or a date must occur literally in the
source text of the page it was read from. Avoid: validation.

**Reconciliation**: opening balance plus the bookings equals the closing balance, checked per
row on the running balance, per page and over the whole statement. Its verdict is one sentence:
`ok`, `failed` or `not_checkable`. See ADR 0011. Avoid: balance check, audit.

**Flagged row**: an extracted row a guard would not pass. It is never dropped and never
committed silently: it goes to the review step, where it is accepted, corrected or dropped.
Avoid: invalid row, error row.

**Column mapping**: which column of an uploaded CSV is the date, the amount (or the debit and
credit pair), the description and the counterparty, plus its date format and decimal separator.
Always shown to the user before a commit, on the Question card the chat asks it with. Not to be
confused with a Category rule, which the glossary
keeps clear of the word mapping. Avoid: schema, layout.

**Attachment**: a file dropped into the chat composer, stored per conversation and identified by
its file name, which is also the handle the `import_file` tool takes. The bytes never enter the
prompt. Avoid: upload (an upload is what the REST import endpoints take), file part.

**Transaction draft**: one booking extracted from what the user typed or pasted, stored with a
short ref and inert until they confirm it on the preview card. Confirming writes the booking
from the draft, never from figures the model retyped. Avoid: proposal, pending transaction.

**Preset**: a column mapping recognized from the header of a known bank (Sparkasse, DKB, ING,
N26, comdirect, Trade Republic). A preset never calls a model. Avoid: template, profile.

**Changeset**: an agent-proposed bulk mutation with an exact preview of affected rows, inert
until applied through the UI. Applying is deterministic code. Avoid: patch, batch edit,
proposal.

**Changeset status**: `proposed` until the user acts, then `applied` or `discarded`. `stale`
when the rows moved after the preview was computed, so it refuses to apply. `superseded` when a
newer changeset for the same rows arrived. An applied changeset that was undone becomes
`discarded` with its applied time still on it. Avoid: pending, cancelled, expired.

**Preference record**: a prompt, a chosen output, a rejected output, the kind (answer or
chart), the SQL and chart code involved, and the rating (`up`, `down` or `pick`). A thumb fills
one side (up the chosen, down the rejected), a pick fills both, which is what a DPO export
reads. One record per rated thing, so a second click replaces it. Training data for the
adapters. Avoid: feedback, rating (the rating is one field of the record).

**Merchant token**: the scrubbed merchant string that is the only thing allowed to leave the
machine for a web lookup. Never amounts, dates, IBANs, card numbers or personal names. Avoid:
query, search term.

**Outbound log**: every request that ever left the machine, written before it is sent. Avoid:
audit log, history.

**Web lookup cache**: what one web lookup found about a merchant token, kept per profile so
that token never leaves twice. Avoid: cache (unqualified), lookup history.

**Evidence**: the one sentence a finished lookup quotes out of a snippet or a page it read,
held to occurring there word for word before it is shown, the way an extracted figure is held
to its page. It is what the card puts under the summary, with the source it came from. Avoid:
citation (a citation is a source URL), snippet, proof.

**Store**: the shop a receipt's printed header names, once the seed dictionary or a web lookup
has recognized it: a title, a category and one line about what it sells. It titles the draft and
gives the legs of a split their one line of context. Only the header is ever resolved, never a
line item. Avoid: merchant (a merchant is what a booking names), vendor, chain.

## Conversation

**Conversation**: profile-scoped, with a title, a model slot, a rolling summary and its turns.
A turn is one agent run: the user's message plus everything the assistant produced for it,
stored both as Pydantic AI message history and as AI SDK UI messages. A turn can be marked
interrupted when Stop cut it short. Avoid: chat, thread, session.

**Running turn**: the turn a conversation is producing right now. It is a task the app owns, not
the request that asked for it, so it survives a reload, a switch of conversation and a closed
tab; a browser that comes back subscribes to the same stream from its first chunk. At most one
per conversation, and Stop is the only thing that ends one early. A conversation, a conversation
list row and an import row all report whether one is running, which is what the spinner and the
closed composer are drawn from. See ADR 0012. Avoid: job, background task (the task is how it is
built, the running turn is what it is).

**Question card**: the card in the transcript that asks the user for a decision only they can
make, with buttons per row and a free text field. It is the `ask_user` tool: the run ends with
the call pending and resumes from the answer, so no model slot waits for a human. Used for
uncertain categorization, duplicate decisions, a mapping confirmation and extraction review.
See ADR 0008. Avoid: prompt, dialog, confirmation.

**Memory**: a durable fact with text, kind (rule, preference, fact) and source (explicit or
distilled), created from a turn and shared across all conversations of the profile. Avoid:
note, knowledge.

**Rolling summary**: the text that replaces turns older than the last six once history passes
sixty percent of the slot's context. Stored on the conversation with a summary-through marker,
shown as a divider in the transcript, editable. Avoid: compaction, compression (those are the
process, the summary is the artifact).

## Charts

**Chart**: one drawing inside an answer, made of a shape, a title, the executed SQL, its rows
and the JavaScript the chart sub-agent wrote against the chart runtime. Avoid: graph, plot,
visualization, figure.

**Shape**: which chart a request wants, one of line, area, bar, bar horizontal, bar grouped, bar
stacked, doughnut and sankey. The shape is chosen in the plan pass and is what the self-check
holds the code to. Avoid: chart type, kind.

**Chart runtime**: the sandboxed page that hosts React and TanStack Charts, receives rows, code
and theme colours by postMessage and draws one chart. Its contract (the allowlisted globals, the
shapes, the house rules) is `docs/chart-runtime.md`. Avoid: renderer, iframe (the iframe is how
the card embeds it, not what it is).

**Self-check**: the in-process run of generated chart code in QuickJS against recording stubs,
whose findings are the repair instructions the sub-agent gets back. Avoid: validation, linting.

**Dashboard card**: one chart a profile keeps on its Dashboard page: a title, a shape, the SQL
and the checked definition, and never a figure. The statement is re-run through the same guard
and the same profile-scoped view on every load, so the numbers are the data's and a statement
that stopped running is a sentence on that card. A card is seeded (one of four defaults) or kept
from a chart in a chat, by the agent itself or by Add to dashboard. Avoid: widget, tile (a tile
is one of the four plain figures above the cards), pin (the verb is fine, the noun is the card).

**One-time chart** and **long-term chart**: which of the two a chart in a chat is. A one-time
chart answers this question and lives in its transcript; a long-term chart is also a dashboard
card, and the chart card says "On the dashboard" either way it got there. The chat agent decides
by passing `keep` to the `chart` tool, and a wrong call costs one click. Avoid: pinned chart,
saved chart.

**Date range**: the two days the whole Dashboard is narrowed to, chosen with the presets or the
two date fields. It reaches the guard's temp view, so the tiles and every stored statement see
those days and nothing else, and the newest booking a card counts back from becomes the range's
own newest. Nothing about it is stored: it lives in the page's search params. Avoid: filter,
period (a period is what a chart is about).

## Models

**Model slot**: one of two logical positions, **fast** and **quality**. The chat agent uses the
slot chosen in the conversation, sub-agents always use fast. Fast is Gemma 4 E4B and quality is
Qwen3.5 9B, on either provider, and the selector labels them with those names; what a
conversation stores and every module passes around is still the slot. A profile has a default
slot, chosen in onboarding, that a new conversation of it starts on. Avoid: model name, tier,
engine.

**Provider**: the setting (FINQUERY_PROVIDER) that resolves each slot to a concrete model:
openrouter during development, local for the demo and hand-in. See ADR 0002. Avoid: backend,
vendor.

**Sub-agent**: a Pydantic AI agent the chat agent delegates to for one job (query, chart,
categorizer, extraction, memory distillation). Always on the fast slot. Avoid: tool (a tool is
what the chat agent calls; the sub-agent is what runs behind it), worker.

**Wire format**: how one local model writes a whole turn into a single text stream: the markers
around its thinking, the syntax of its tool calls, and what its chat template calls the
reasoning of an earlier assistant message. Gemma 4 and Qwen3.5 have one each, so the local
provider has one module each and picks it from the model, not from the slot. Avoid: chat format
(llama.cpp's word for the template itself), protocol.

**Adapter**: a LoRA adapter attached to the fast slot for one sub-agent (query, chart) on the
local provider. Not to be confused with the Vercel stream adapter, which the code calls the
"stream adapter" or "Vercel adapter". Avoid: fine-tune, checkpoint.

**Audit note**: a short statement attached to a turn about how the answer was produced rather
than about the data, such as a sub-agent having run on the base weights because its adapter file
was missing. It rides the turn metadata, so the transcript keeps it after a reload. Avoid:
warning, disclaimer.
