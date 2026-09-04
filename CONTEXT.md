# FinQuery domain glossary

The words the code, the tickets and the UI use. One meaning per term. Where a synonym is
tempting, it is listed as avoided so the vocabulary stays stable.

## Data

**Profile**: the isolation boundary. Every account, transaction, category, rule, memory,
conversation and preference record belongs to exactly one profile. A default profile is created
at startup. Avoid: user, workspace, account (an account is a bank account, see below).

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
lost: the user answers **Keep both** (insert it) or **Remove** (leave the data as it is), on the
Import page or on a Question card, and the decision stays on the candidate. Avoid: duplicate
(what is a duplicate is the user's call, not ours), conflict, collision.

**Column mapping**: which column of an uploaded CSV is the date, the amount (or the debit and
credit pair), the description and the counterparty, plus its date format and decimal separator.
Always shown to the user before a commit: in the Import page preview, or on a Question card when
the file was dropped into a chat. Not to be confused with a Category rule, which the glossary
keeps clear of the word mapping. Avoid: schema, layout.

**Attachment**: a file dropped into the chat composer, stored per conversation and identified by
its file name, which is also the handle the `import_file` tool takes. The bytes never enter the
prompt. Avoid: upload (an upload is what the Import page takes), file part.

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

## Conversation

**Conversation**: profile-scoped, with a title, a model slot, a rolling summary and its turns.
A turn is one agent run: the user's message plus everything the assistant produced for it,
stored both as Pydantic AI message history and as AI SDK UI messages. A turn can be marked
interrupted when Stop cut it short. Avoid: chat, thread, session.

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

## Models

**Model slot**: one of two logical positions, **fast** and **quality**. The chat agent uses the
slot chosen in the conversation, sub-agents always use fast. Avoid: model name, tier, engine.

**Provider**: the setting (FINQUERY_PROVIDER) that resolves each slot to a concrete model:
openrouter during development, local for the demo and hand-in. See ADR 0002. Avoid: backend,
vendor.

**Sub-agent**: a Pydantic AI agent the chat agent delegates to for one job (query, chart,
categorizer, extraction, memory distillation). Always on the fast slot. Avoid: tool (a tool is
what the chat agent calls; the sub-agent is what runs behind it), worker.

**Adapter**: a LoRA adapter attached to the fast slot for one sub-agent (query, chart) on the
local provider. Not to be confused with the Vercel stream adapter, which the code calls the
"stream adapter" or "Vercel adapter". Avoid: fine-tune, checkpoint.

**Audit note**: a short statement attached to a turn about how the answer was produced rather
than about the data, such as a sub-agent having run on the base weights because its adapter file
was missing. It rides the turn metadata, so the transcript keeps it after a reload. Avoid:
warning, disclaimer.
