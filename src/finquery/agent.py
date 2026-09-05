"""The chat agent: its system prompt, the deps one turn hands it, and its tools.

The model is chosen per run from the conversation's slot. Tools get what they need from
`ChatDeps`, so the agent itself holds no application state. `query`, `chart`, `remember`,
`set_rule`, `review_batch`, `review_duplicates`, `propose_changeset`, `apply_simple_edit`,
`lookup_merchant`, `import_file`, `extract_transaction` and `add_transaction` are the tools,
and each one that needs a model resolves its own slot through the deps.

`propose_changeset` and `apply_simple_edit` are the writing tools. Neither one decides anything
about the data: `finquery.changesets` resolves the intent, refuses what the data model refuses
(and that sentence goes back to the model as a retry), and the user applies through REST.

`ask_user` is the odd one out: it has no function, because a human answers it in the browser.
See `finquery.ask_user` and ADR 0008.

`lookup_merchant` is the other odd one: it is only declared when the profile has web lookup
switched on (its `prepare` reads the switch per run), and when it is off the instructions say
so and say where to turn it on. See `finquery.weblookup`.

Selected memories and the rolling summary arrive as run instructions assembled by
`finquery.context.assemble`, not from here.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from functools import partial
from typing import Any

from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.settings import ModelSettings
from pydantic_ai.tools import DeferredToolRequests, ToolDefinition
from sqlalchemy.orm import Session, sessionmaker

from finquery import attachments
from finquery.ask_user import ask_user_toolset
from finquery.categorize import QUESTIONS_PER_CARD, pending_questions, review_card
from finquery.categorize import set_rule as store_category_rule
from finquery.categorize import split_choice
from finquery.categorize.rules import load_categories, taxonomy_of
from finquery.changesets import ChangesetError, ChangesetIntent, propose, to_out
from finquery.changesets import apply as apply_changeset
from finquery.chart import run_chart
from finquery.db import Profile, SplitSumError
from finquery.edits import TransactionEditError
from finquery.ingest.chat_import import import_attachment
from finquery.ingest.duplicates import PER_CARD as DUPLICATES_PER_CARD
from finquery.ingest.duplicates import review as duplicate_review
from finquery.ingest.typed import add_draft, find_draft, preview_card, propose_transactions, store_drafts
from finquery.memory import MemoryKind, add_memory
from finquery.onboarding import language_rule
from finquery.progress import report as report_progress
from finquery.providers import ModelResolver, ProviderNotAvailable
from finquery.query import load_query_context, run_query
from finquery.weblookup import MAX_FETCHES, MAX_SEARCHES, WebClient, lookups_for, web_lookup_enabled

SYSTEM_PROMPT = """\
You are FinQuery, a local-first personal-finance analyst. You help the user understand their
bank transactions and you answer in the language the user writes in.

The one rule you never break: every number you state comes from the `query` tool. You do no
arithmetic in prose, you never estimate, and you never combine, scale or round figures the tool
did not return. A sum, a count, an average, a share or a comparison is another `query` call, or
one call that returns both figures.

How to use `query`:
- Write a standalone request. The sub-agent that writes the SQL sees neither the conversation
  nor your earlier calls, so a follow-up like "and compared to April" has to become "total
  spending in April 2025 compared with May 2025".
- Always name the period and name the topic the way the user did.
- Ask for totals per group ("per merchant", "per month"), not for a list of single bookings,
  unless the user asked to see the bookings themselves.
- Answer every part of the question: a "which and how much" question needs the breakdown and
  the total, so ask for both in one request.
- Quote the figures from the rows exactly as they came back, never rounded or rescaled. The
  result's `figures` lines write every euro figure the German way: copy a figure from there.
- If the result carries an `error`, say in one line what failed and state no figure.
- If it returns no rows, say the data holds no answer for that question.
- If the question cannot be answered from bank transactions at all (a credit score, a share
  price, next month's rent), call nothing, say in one sentence why it is not in the data, and
  name one question about these transactions you can answer instead.
- Never write SQL yourself and never show SQL in your answer: the transcript already shows the
  statement that ran.

When to use `chart`:
- Call it whenever the user asks for a chart, a graph or a visualization, and whenever the
  answer is a figure over time (a month series, a trend, a running total) or a comparison across
  several categories, merchants or accounts. A single figure needs no chart.
- Write the request the same way as for `query`: standalone, with the period and the topic. The
  chart sub-agent picks the shape, runs its own query and draws it. Name a shape only if the user
  did.
- One chart per answer. Do not call `chart` and `query` for the same figures: the chart's rows
  come from an executed query, so you may quote them.
- Read `rendered` before you write a word about the chart. `rendered: true` means it is on
  screen: say in one or two sentences what it shows, quoting at most the two figures that
  matter. Never describe the code, the columns or the shape, and never write chart code
  yourself.
- `rendered: false` means there is no picture, whatever else the result carries. Say in one line
  that the chart could not be drawn, give the reason from `error` in plain words, and answer with
  the figures from its `rows` instead. Never name a shape, an axis, a colour or a trend of a
  chart that was not drawn: there is nothing there to describe.
- The chart tool always ends your turn with text. Writing that text is the last step of the
  turn, never something to leave for the next one.

Changing the data. You never write to a booking on a hunch: first call `query` for the rows,
asking for their `id` alongside the columns you need ("the id, date, description and amount of
every booking from Netflix"), so a change names real rows.

- `apply_simple_edit` is for one row the user pointed at and one change they spelled out ("set
  this one to Dining", "that Edeka booking was 42.30"). It applies immediately and the user
  gets an Undo button, so say in one line what you changed.
- `propose_changeset` is for everything else: more than one row, a split, a delete, a change to
  the categories, or anything the user did not literally ask for. It writes nothing. The user
  sees a card with the exact rows and presses Apply or Discard, so describe what you proposed
  and never say it has happened.
- A request to move bookings that already exist ("recategorize all Netflix rows as
  Subscriptions", "alle Edeka-Buchungen zu Lebensmitteln") is a bulk change: use
  `propose_changeset` and never `set_rule`, so the user sees the exact rows before they move.
- A split needs at least two legs in cents that add up to the booking exactly, negative for
  spending. If a tool refuses, read the sentence it gives you and correct the call once.
- Adding, renaming, merging or deleting a category or subcategory is `propose_changeset` with
  kind `taxonomy`.

When the user tells you something durable about their finances (what a merchant is, that
PayPal payments to Anna are dinner, which categories they care about), call `remember` once
with one short sentence and confirm it in a single line of your answer. Memories are shared by
every conversation of this profile, so never store a one-off question or a figure. Anything
already remembered is given to you at the top of these instructions, and it is there to be
used: when a memory names the person or merchant behind a word the user wrote ("my flatmate"
is Max Schulz, "my landlord" is Hausverwaltung Bergmann), write that name into the `query`
request, because the sub-agent sees the request and nothing else.

Categories and rules:
- A booking with no category is `Needs review`. `Unknown` is a category only the user assigns,
  never you.
- A category rule is the user's own pattern to category mapping and the highest-priority
  categorization stage. `set_rule` stores one and immediately recategorizes every booking of
  that merchant in the profile.
- `set_rule` is only for a statement about a merchant, now and in future ("PayPal to Anna is
  always Dining", "Rewe ist immer Lebensmittel"). Call it and confirm in one line with the
  figures it returned. Never say a rule was stored without calling the tool.
- The pattern is the merchant as it appears in the booking text ("Anna Weber", "REWE"), never a
  whole sentence, never a booking id and never a phrase like "all Netflix rows".
- `review_batch` returns the merchants that still need the user's decision as a ready `card`.
  Show that card with `ask_user` unchanged: the same title, the same note, the same rows and
  the same `apply` object. Never rewrite it and never build one of your own.
- An answered Question card is already done when you see it: the rules were stored and the
  bookings moved before you were called again, and the tool result's `applied` line says
  exactly what happened. Say it back in one or two sentences and make no `set_rule` call for
  it. A row with no answer stays Needs review and is never guessed at.
- Then call `review_batch` again and ask the next card, until nothing is pending or the user
  asks you to stop. When nothing is pending, say so in one line.

Answer in the language of the user's newest message, whatever language the conversation used
before it: a German question gets a German answer, an English question an English one, even in
the same conversation. Write money the German way, comma for the decimals, dot for the
thousands, EUR after the number: 1.234,56 EUR, 843,60 EUR. Dates the same way: 04.09.2026.

Files the user attaches:
- `import_file` is what turns an attached file into transactions. Call it once per file, with
  the file name exactly as the list of attached files spells it, and pass `account_name` only
  when the user named an account.
- A CSV from a bank we recognize is imported straight away. For an unknown layout the tool comes
  back asking for the column mapping to be confirmed: show its `card` with `ask_user`
  unchanged, and when the user confirms, call `import_file` again for the same file with
  `confirmed=true`.
- When a file is imported the tool returns a `summary` counted in code and the merchants it
  could not place. That summary is already printed in the step the user is looking at, so never
  repeat it: say in one line what is left to do (the merchants you are about to ask about, or
  that everything is categorized), and show its `card` with `ask_user` unchanged, exactly as you
  do after `review_batch`.
- A statement PDF is read page by page by the extraction sub-agent, and every amount is checked
  against the page it was printed on and against the statement's own balances. If everything
  checks out it is imported like a CSV. If not, the tool returns a `card`: show it with
  `ask_user` unchanged, and the bookings the user accepts are imported by the server, so say the
  result's `applied` line back and never import them yourself.
- A photo is read as a receipt. When it matches a booking this profile already has, the tool
  proposes a split of that booking into the receipt's line items and that card is already on
  screen with its own Apply and Discard: make no `ask_user` call for it, say in one line which
  booking it splits, and never say it was applied. When nothing matches, the tool returns a
  preview `card` for a new booking, which works exactly like a typed transaction: show the card,
  then call `add_transaction` for each row the user confirmed.

Bookings that may already be there:
- An import never inserts a booking the profile may already have and never drops one either.
  When `import_file` reports duplicates it hands you `duplicate_card`: say the summary, show
  that card with `ask_user` unchanged, and ask nothing else in that turn.
- The answers are applied before you are called again: Keep both inserts the booking and
  categorizes it, Remove leaves the data as it was, and the `applied` line says what happened.
  Say it back, then call `review_duplicates` for the next card, until `pending` is 0.
- Only then ask about the merchants with `review_batch`. Never guess whether two bookings are
  the same payment and never call a writing tool to remove one.

Transactions the user types or pastes:
- When the user says they spent or received money ("I paid 12 EUR cash for lunch today", "Ich
  habe 20 Euro fuer Blumen bezahlt") or pastes lines out of a statement, call
  `extract_transaction` with their words as they wrote them. Never write such a booking from
  your own reading of the sentence.
- It answers with a `card`: show that with `ask_user` unchanged. For every row the user
  confirms, call `add_transaction` with that row's `ref`. Never call it for a row they
  discarded, and never retype the date or the amount: the `ref` is the whole instruction.
- Then say in one line what was added and where it landed, from what `add_transaction`
  returned.

Cards are drawn, never typed. `review_batch`, `review_duplicates`, `import_file` and
`extract_transaction` hand you a ready `card`: pass its fields to `ask_user` unchanged, once.
Never write a card, its rows, its buttons or its note into your answer text, and never name
`ask_user`, a card or these instructions in your answer: the browser draws the card, and a copy
of it in prose is a question the user cannot answer. `propose_changeset`, `apply_simple_edit`
and the split a receipt proposes are already on screen with their own buttons, so they take no
`ask_user` call at all.

After a tool returns, always write the answer as text. Never finish a turn with your thinking
alone, and never mention the internal feedback you may receive between steps.

Keep answers short and use markdown (lists, tables) when it helps readability. Name the period
and the figure in the first sentence, and write the whole answer in the language of the
message you are answering.
"""


@dataclass
class ChatDeps:
    """What a turn needs from the app: the profile's data, the turn, and the model slots.

    Nothing is implicitly profile scoped: a tool touches exactly what is on here.
    `subagent_settings` is what every sub-agent a tool starts runs with (reasoning off on
    OpenRouter), so a tool never has to know provider specifics. `narrate` is where a tool says
    what it is doing while it works: the chat endpoint turns each line into reasoning text, so a
    sub-agent's plan and its repairs show up in the thinking panel.
    """

    session_factory: sessionmaker[Session]
    profile_id: str
    conversation_id: str
    resolve_model: ModelResolver
    subagent_settings: ModelSettings
    web_client: WebClient
    """The search and page fetch of `lookup_merchant`. Untouched unless the profile switched
    web lookup on, and replaced by a stub in tests."""
    narrate: Callable[[str], None] = field(default=lambda _text: None)


# `ask_user` has no function here: it is a deferred tool, so a run that calls it ends with the
# call pending and `DeferredToolRequests` as its output, which is what lets a human answer
# without a model slot being held open.
chat_agent: Agent[ChatDeps, str | DeferredToolRequests] = Agent(
    instructions=SYSTEM_PROMPT,
    deps_type=ChatDeps,
    output_type=[str, DeferredToolRequests],
    toolsets=[ask_user_toolset],
    name="finquery-chat",
)


@chat_agent.instructions
def data_brief(ctx: RunContext[ChatDeps]) -> str:
    """What the profile holds right now, so a question can be judged before it is queried."""
    with ctx.deps.session_factory() as session:
        context = load_query_context(session, ctx.deps.profile_id)
    if context.transaction_count == 0:
        return (
            "This profile has no transactions yet. Do not call `query` or `chart`, and do not state any number: "
            "tell the user the profile is empty and that a bank statement, a CSV export or a photo can "
            "be dropped into this chat and you will import it."
        )
    # The subcategories are here because a changeset names them, and a name it invents is refused.
    taxonomy = "; ".join(f"{name} ({', '.join(subs)})" if subs else name for name, subs in context.taxonomy)
    lines = [
        f"Today is {context.today.isoformat()}. The profile holds {context.transaction_count} bookings from "
        f"{context.first_booked_on} to {context.last_booked_on} in {', '.join(context.accounts)}.",
        f"Categories, with their subcategories: {taxonomy}.",
    ]
    if context.categorized_count == 0:
        lines.append(
            "No booking is categorized yet, so ask `query` for a topic in plain words (it knows the "
            "merchants) and do not ask it to filter by category."
        )
    elif context.categorized_count < context.transaction_count:
        lines.append(
            f"{context.transaction_count - context.categorized_count} bookings are still Needs review. "
            "`review_batch` is how you ask about them."
        )
    return "\n".join(lines)


@chat_agent.instructions
def answer_language(ctx: RunContext[ChatDeps]) -> str:
    """The language this answer is written in, named outright.

    The profile's choice when it made one in onboarding, which has to beat the
    follow-the-message rule and says so. Otherwise the language of the newest message, detected
    in code from its function words, because the local fast model left to detect it by itself
    answers German data in German whatever the question was. See `finquery.onboarding`.
    """
    prompt = ctx.prompt if isinstance(ctx.prompt, str) else None
    with ctx.deps.session_factory() as session:
        profile = session.get(Profile, ctx.deps.profile_id)
        return language_rule(profile.answer_language if profile else "follow", prompt)


@chat_agent.instructions
def attached_files(ctx: RunContext[ChatDeps]) -> str:
    """The files dropped into this conversation, by name, with what has happened to them.

    The bytes never enter the prompt (a bank CSV would be tens of thousands of tokens): the file
    name is the handle, and `import_file` reads the stored file. It is an instruction rather than
    part of the user's message so that a later turn still knows the file is there.
    """
    with ctx.deps.session_factory() as session:
        return attachments.brief(attachments.of_conversation(session, ctx.deps.conversation_id))


@chat_agent.tool
async def query(ctx: RunContext[ChatDeps], request: str, hints: str | None = None) -> dict[str, Any]:
    """Answer one question about the user's transactions with SQL that really ran.

    The query sub-agent writes the statement, a guard admits only a read-only SELECT over this
    profile's transactions, and the rows come back with the statement that produced them. This
    is the only source of numbers you have.

    Args:
        request: The question in plain words, standing on its own: the period, the topic and
            what to compute, without referring to the conversation. German or English.
        hints: Optional extra instruction for the SQL, for instance which column to group by or
            which merchants belong to the topic.
    """
    outcome = await run_query(
        resolve_model=ctx.deps.resolve_model,
        model_settings=ctx.deps.subagent_settings,
        session_factory=ctx.deps.session_factory,
        profile_id=ctx.deps.profile_id,
        request=request,
        hints=hints,
    )
    return outcome.payload()


@chat_agent.tool(retries=2)
def propose_changeset(ctx: RunContext[ChatDeps], intent: ChangesetIntent) -> dict[str, Any]:
    """Propose a change to the user's bookings or categories, for them to apply or discard.

    Nothing is written. The selection is resolved and validated here and the exact rows it would
    touch come back as a preview, which the user sees as a card with Apply and Discard. Use this
    for anything touching more than one booking, for a split, for a delete, for a change to the
    categories, and for anything the user did not literally ask for.

    A refusal comes back as a sentence: read it and correct the call once.
    """
    with ctx.deps.session_factory() as session:
        try:
            changeset = propose(
                session, ctx.deps.profile_id, intent, conversation_id=ctx.deps.conversation_id
            )
            out = to_out(changeset)
        except (TransactionEditError, SplitSumError, ChangesetError) as exc:
            session.rollback()
            raise ModelRetry(str(exc)) from exc
        session.commit()
    return out.model_dump(mode="json")


@chat_agent.tool(retries=2)
def apply_simple_edit(
    ctx: RunContext[ChatDeps],
    transaction_id: str,
    title: str,
    category: str | None = None,
    subcategory: str | None = None,
    description: str | None = None,
    amount_cents: int | None = None,
    booked_on: date | None = None,
) -> dict[str, Any]:
    """Change one booking the user pointed at, immediately, with an Undo button.

    Only for a single row and a change the user spelled out ("set this one to Dining", "that
    Edeka booking was 42.30"). Anything broader, anything you inferred, and every split, delete
    or category change is `propose_changeset` instead. The `undo_token` in the result is what
    the Undo button reverts, so the user can always take it back.

    Args:
        transaction_id: The booking's id, as a query returned it.
        title: One short line naming the change, for the card.
        category: The category to put it in.
        subcategory: The subcategory, inside that category.
        description: A new description, when the user corrected the text.
        amount_cents: A new amount in cents, negative for spending.
        booked_on: A new booking date.
    """
    intent = ChangesetIntent(
        kind="edit",
        title=title,
        transaction_ids=[transaction_id],
        category=category,
        subcategory=subcategory,
        description=description,
        amount_cents=amount_cents,
        booked_on=booked_on,
    )
    with ctx.deps.session_factory() as session:
        try:
            changeset = propose(
                session, ctx.deps.profile_id, intent, conversation_id=ctx.deps.conversation_id
            )
            apply_changeset(session, ctx.deps.profile_id, changeset)
            out = to_out(changeset)
        except (TransactionEditError, SplitSumError, ChangesetError) as exc:
            session.rollback()
            raise ModelRetry(str(exc)) from exc
        session.commit()
    # The changeset is the undo token: one POST to /api/changesets/{id}/undo puts it back.
    return {**out.model_dump(mode="json"), "undo_token": out.id}


@chat_agent.tool
def remember(ctx: RunContext[ChatDeps], text: str, kind: MemoryKind = "fact") -> str:
    """Remember one durable fact about the user or their transactions across all conversations.

    Args:
        text: The fact as one short sentence, phrased to still make sense months later.
        kind: "rule" for a mapping you should apply, "preference" for what the user cares
            about or how they want answers, "fact" for everything else.
    """
    with ctx.deps.session_factory() as session:
        memory = add_memory(
            session,
            ctx.deps.profile_id,
            text,
            kind=kind,
            source="explicit",
            created_from=ctx.deps.conversation_id,
        )
        session.commit()
        if memory is None:
            return f"Already remembered, nothing to do: {text}"
        return f"Remembered: {memory.text}"


# A Question card usually comes back with several answers at once, so the model emits several
# `set_rule` calls in one response. They write, and SQLite serializes writers, so they run one
# after another instead of racing for the same connection.
@chat_agent.tool(sequential=True)
def set_rule(
    ctx: RunContext[ChatDeps], pattern: str, category: str, subcategory: str | None = None
) -> dict[str, Any]:
    """Teach the profile where a merchant belongs, for good.

    Stores a category rule and applies it right away to every booking in the profile whose
    text contains the pattern, including ones another stage had placed differently. The rule is
    then the highest-priority stage, so the same merchant is never asked about again.

    Only for a statement about a merchant. A request to move bookings that already exist is
    `propose_changeset`, so the user sees the rows before they move.

    Args:
        pattern: The merchant as it appears in the booking text, for instance "REWE" or
            "Anna Weber". Not a sentence, not a booking id. Case and punctuation do not matter.
        category: One of the profile's categories, spelled as the profile spells it. A combined
            "Groceries > Supermarket" is accepted and split for you.
        subcategory: One of that category's subcategories, or nothing.
    """
    head, tail = split_choice(category)
    with ctx.deps.session_factory() as session:
        outcome = store_category_rule(
            session, ctx.deps.profile_id, pattern=pattern, category=head, subcategory=subcategory or tail
        )
    return outcome.payload()


@chat_agent.tool
async def review_batch(ctx: RunContext[ChatDeps], limit: int = QUESTIONS_PER_CARD) -> dict[str, Any]:
    """The merchants that still need the user's decision, as a ready Question card.

    `card` is the whole question, already written: show it with `ask_user` unchanged, the way
    you do with `review_duplicates`. `questions` is the same rows in detail, for the step the
    transcript renders. Never ask about a merchant this did not return.

    Args:
        limit: How many merchants to ask about at once, at most five.
    """
    lookups = lookups_for(
        ctx.deps.session_factory,
        ctx.deps.profile_id,
        client=ctx.deps.web_client,
        resolve_model=ctx.deps.resolve_model,
        model_settings=ctx.deps.subagent_settings,
    )
    with ctx.deps.session_factory() as session:
        questions, pending = await pending_questions(
            session,
            ctx.deps.profile_id,
            resolve_model=ctx.deps.resolve_model,
            model_settings=ctx.deps.subagent_settings,
            # None when the profile has web lookup off, and then no merchant is looked up for a
            # card either.
            lookups=lookups,
            limit=max(1, min(limit, QUESTIONS_PER_CARD)),
        )
    return {
        "pending_merchants": pending,
        "questions": [question.payload() for question in questions],
        # The card is built here rather than by the model: it carries the `apply` object that
        # makes the answers become rules in code, and its copy is written once (real plurals,
        # "3 merchants I am not sure about") instead of being invented per turn.
        "card": review_card(questions, pending).model_dump(mode="json") if questions else None,
    }


@chat_agent.tool
async def review_duplicates(ctx: RunContext[ChatDeps], limit: int = DUPLICATES_PER_CARD) -> dict[str, Any]:
    """The bookings held aside as possible duplicates, ready to become a Question card.

    An import never inserts a booking the profile may already have and never drops one either:
    it holds it aside with the booking it matched. This returns the next batch as a ready
    `card`, which you show with `ask_user` unchanged. The answers are applied in code before
    you are called again (Keep both inserts the booking and categorizes it, Remove discards
    it), so call this again after each answered card until `pending` is 0. It writes nothing
    itself.

    Args:
        limit: How many candidates to ask about at once, at most five.
    """
    with ctx.deps.session_factory() as session:
        return duplicate_review(session, ctx.deps.profile_id, limit=limit)


@chat_agent.tool
async def chart(ctx: RunContext[ChatDeps], request: str, hints: str | None = None) -> dict[str, Any]:
    """Draw one chart of the user's transactions and show it in the answer.

    The chart sub-agent plans the shape, gets its rows through the same query path as `query`,
    writes the chart and checks it before it is shown. `rendered` says whether a chart really
    reached the screen: true means it is visible and needs no description, false means there is
    none and the answer has to give the figures from `rows` instead.

    Whatever it returns, write your answer as text in the same turn.

    Args:
        request: What to chart, in plain words and standing on its own: the period, the topic
            and what to compare, plus the shape if the user named one. Write it in the language
            of the user's newest message: the chart's caption and its month labels follow it.
        hints: Optional extra instruction, for instance which categories to include.
    """
    outcome = await run_chart(
        resolve_model=ctx.deps.resolve_model,
        model_settings=ctx.deps.subagent_settings,
        session_factory=ctx.deps.session_factory,
        profile_id=ctx.deps.profile_id,
        request=request,
        hints=hints,
        narrate=ctx.deps.narrate,
    )
    return outcome.payload()


# Web lookup is off by default, per profile. Both halves of that read the same switch: the
# instructions below tell the model whether it has the tool and, when it does not, where the
# user turns it on, and `prepare` decides whether the tool is declared at all.
WEB_LOOKUP_ON = """\
Unknown merchants:
- `lookup_merchant` finds out what a merchant is by searching the web itself, deciding how many
  searches and page reads it needs (at most {searches} searches and {fetches} page reads).
- Only the scrubbed merchant name leaves this machine: never an amount, a date, an account
  number or a person's name, and a booking whose merchant reads as a person is refused. Every
  request is written to the outbound log the user can read in Settings.
- Call it when the user asks what a merchant is, or before you place a booking whose merchant
  you do not recognize. Pass the merchant as it stands in the booking text.
- Call it even when this conversation already looked the merchant up and you could answer from
  what was said: the second call answers from this profile's own cache without anything leaving
  the machine, and the step it renders is the only proof the user has of that. Answering a
  repeated merchant question out of the conversation, with no step, takes that proof away.
- Say what it found in one or two lines and name the category it suggests. The sources it used
  are shown under your answer, so never list URLs yourself.
- It is not a source of figures. Numbers still come from `query` only.
- If it comes back with an `error`, say that one line and place nothing."""

WEB_LOOKUP_OFF = """\
Unknown merchants: web lookup is switched off for this profile, so you cannot look a merchant
up and nothing about these transactions can leave this machine. If the user asks what an
unknown merchant is, say that web lookup is off and that it can be switched on in Settings
under Web lookup, and offer to file the booking from what the booking text says instead."""


@chat_agent.instructions
def web_lookup_brief(ctx: RunContext[ChatDeps]) -> str:
    """Whether this profile lets a merchant token leave, and what that means for this turn."""
    with ctx.deps.session_factory() as session:
        enabled = web_lookup_enabled(session, ctx.deps.profile_id)
    if not enabled:
        return WEB_LOOKUP_OFF
    return WEB_LOOKUP_ON.format(searches=MAX_SEARCHES, fetches=MAX_FETCHES)


def _only_when_web_lookup_is_on(ctx: RunContext[ChatDeps], tool_def: ToolDefinition) -> ToolDefinition | None:
    """Declare `lookup_merchant` only for a profile that switched web lookup on.

    Read per run, so a switch flipped in Settings takes the tool away from the next turn. A
    model that never sees the tool cannot call it, which is the first half of "off means
    nothing leaves"; the second half is that the tool itself refuses too.
    """
    with ctx.deps.session_factory() as session:
        return tool_def if web_lookup_enabled(session, ctx.deps.profile_id) else None


@chat_agent.tool(prepare=_only_when_web_lookup_is_on)
async def lookup_merchant(ctx: RunContext[ChatDeps], merchant: str) -> dict[str, Any]:
    """Find out what an unknown merchant is by searching the web.

    Scrubs the merchant down to a token (no amounts, no dates, no account or reference numbers,
    no personal names), answers from the profile's cache when that token was looked up before,
    and otherwise runs a search loop that decides for itself how many searches and page reads
    it needs. Returns what the merchant is, a suggested category with a confidence, and the
    sources it relied on.

    Args:
        merchant: The merchant as it stands in the booking text or as the user named it, for
            instance "KARLS DANKT" or "Xbox Game Pass". Not a whole sentence, no amount, no
            date and no booking id.
    """
    lookups = lookups_for(
        ctx.deps.session_factory,
        ctx.deps.profile_id,
        client=ctx.deps.web_client,
        resolve_model=ctx.deps.resolve_model,
        model_settings=ctx.deps.subagent_settings,
    )
    if lookups is None:
        return {
            "merchant": merchant,
            "error": "Web lookup is switched off for this profile. It can be switched on in Settings.",
        }
    with ctx.deps.session_factory() as session:
        taxonomy = taxonomy_of(load_categories(session, ctx.deps.profile_id))
    lookup = await lookups.merchant(merchant, None, taxonomy)
    return lookup.payload()


@chat_agent.tool
async def import_file(
    ctx: RunContext[ChatDeps],
    file_name: str,
    account_name: str | None = None,
    confirmed: bool = False,
) -> dict[str, Any]:
    """Import a file the user attached to this conversation.

    Runs the pipeline behind `/api/imports`: it reads the CSV, takes the preset of a bank we
    recognize or asks for a proposed mapping to be confirmed, commits the bookings the profile
    does not have yet, and categorizes them. Every figure it returns was counted while it ran.
    Progress appears in the transcript while it works, so nothing has to be reported in prose.

    Args:
        file_name: The attached file, spelled as the list of attached files spells it.
        account_name: The account the bookings belong to, only when the user named one.
            Otherwise the bank of the export decides.
        confirmed: True only when you are calling again after the user confirmed the column
            mapping on the card this tool asked with.
    """
    with ctx.deps.session_factory() as session:
        return await import_attachment(
            session,
            ctx.deps.profile_id,
            ctx.deps.conversation_id,
            file_name=file_name,
            account_name=account_name,
            confirmed=confirmed,
            resolve_model=ctx.deps.resolve_model,
            model_settings=ctx.deps.subagent_settings,
            report=partial(report_progress, ctx),
        )


@chat_agent.tool
async def extract_transaction(ctx: RunContext[ChatDeps], text: str) -> dict[str, Any]:
    """Read the bookings out of what the user typed or pasted, as a preview they confirm.

    Writes nothing. It stores a draft per booking and returns the card to show: the user
    confirms or discards each row, and `add_transaction` writes the confirmed ones from the
    stored draft, so the amount that lands is the amount that was shown.

    Args:
        text: What the user wrote, as they wrote it: the sentence about the payment or the
            statement lines they pasted. German or English.
    """
    with ctx.deps.session_factory() as session:
        context = load_query_context(session, ctx.deps.profile_id)
        try:
            model = ctx.deps.resolve_model("fast")
            proposals = await propose_transactions(
                text,
                today=context.today,
                accounts=list(context.accounts),
                model=model,
                model_settings=ctx.deps.subagent_settings,
            )
        except ProviderNotAvailable as exc:
            return {"status": "unavailable", "error": str(exc)}
        except Exception as exc:  # noqa: BLE001 - a failed extraction is a message, not a crash
            return {"status": "failed", "error": f"The booking could not be read: {exc}"}
        drafts, problems = store_drafts(session, ctx.deps.profile_id, ctx.deps.conversation_id, proposals)
        if not drafts:
            return {
                "status": "nothing_found",
                "error": "No booking with a date and an amount could be read from that text.",
                "problems": problems,
            }
        card = preview_card(drafts)
        return {
            "status": "preview",
            "drafts": [
                {
                    "ref": draft.ref,
                    "booked_on": draft.booked_on.isoformat(),
                    "amount_cents": draft.amount_cents,
                    "description": draft.description,
                    "counterparty": draft.counterparty,
                    "account": draft.account_name,
                }
                for draft in drafts
            ],
            "problems": problems,
            "card": card.model_dump(mode="json"),
            "instruction": (
                "Show this `card` with `ask_user`, unchanged. Then call `add_transaction` once "
                "per row the user confirmed, with that row's `ref`."
            ),
        }


# One confirmed card can hold several rows, so the model emits several calls in one response.
# They write, and SQLite serializes writers, so they run one after another.
@chat_agent.tool(sequential=True)
async def add_transaction(
    ctx: RunContext[ChatDeps], ref: str, booked_on: str | None = None
) -> dict[str, Any]:
    """Write one transaction the user confirmed on a preview card, and categorize it.

    The booking is written from the stored draft, not from anything you pass here, so the ref is
    all it takes. Calling it twice for the same ref adds nothing.

    If the booking looks like one the profile already has, nothing is written and it comes back
    with a `card` instead: show that with `ask_user` unchanged, the same as for an import.

    Args:
        ref: The `ref` of the confirmed row, for instance `t1`.
        booked_on: Only when the card asked the user for a date, because a receipt's own date
            could not be read, and they typed one: pass it exactly as they wrote it
            (`04.09.2026`). Leave it out otherwise, and never write a date of your own.
    """
    with ctx.deps.session_factory() as session:
        draft = find_draft(session, ctx.deps.conversation_id, ref)
        if draft is None:
            return {"status": "no_such_draft", "ref": ref, "error": f"No preview row called {ref!r}."}
        return await add_draft(
            session,
            ctx.deps.profile_id,
            draft,
            booked_on=booked_on,
            resolve_model=ctx.deps.resolve_model,
            model_settings=ctx.deps.subagent_settings,
        )
