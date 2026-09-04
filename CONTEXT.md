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
found, reconciliation result. Avoid: upload, sync.

**Column mapping**: which column of an uploaded CSV is the date, the amount (or the debit and
credit pair), the description and the counterparty, plus its date format and decimal separator.
Always shown to the user before a commit. Not to be confused with a Category rule, which the
glossary keeps clear of the word mapping. Avoid: schema, layout.

**Preset**: a column mapping recognized from the header of a known bank (Sparkasse, DKB, ING,
N26, comdirect, Trade Republic). A preset never calls a model. Avoid: template, profile.

**Changeset**: an agent-proposed bulk mutation with an exact preview of affected rows, inert
until applied through the UI. Applying is deterministic code. Avoid: patch, batch edit,
proposal.

**Preference record**: a prompt, a chosen output, a rejected output, the kind (answer or
chart), the SQL and chart code involved, and the rating. Training data for the adapters.
Avoid: feedback, rating (the rating is one field of the record).

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
