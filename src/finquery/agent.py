"""The chat agent: its system prompt, the deps one turn hands it, and its tools.

The model is chosen per run from the conversation's slot. Tools get what they need from
`ChatDeps`, so the agent itself holds no application state. `query`, `chart`, `remember`,
`set_rule`, `review_batch`, `review_duplicates`, `propose_changeset`, `apply_simple_edit`,
`lookup_merchant`, `import_file`, `extract_transaction`, `add_transaction` and the five
dashboard tools (`dashboard_charts`, `show_dashboard_chart`, `edit_dashboard_chart`,
`rename_dashboard_chart`, `remove_dashboard_chart`) are the tools, and each one that needs a
model resolves its own slot through the deps.

A chart the agent marks `keep` becomes a dashboard card from inside the `chart` tool, so the
dashboard is filled from the chat and from nowhere else. The three tools that change a card
apply at once and stash the version they replaced, which is the Undo the card in the transcript
offers (`finquery.dashboard`).

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

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from functools import partial, wraps
from inspect import iscoroutinefunction
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
from finquery.chart.subagent import previous_hint
from finquery.dashboard import apply_edit as apply_dashboard_edit
from finquery.dashboard import card_chart, keep_chat_chart
from finquery.dashboard import cards_of as dashboard_cards_of
from finquery.dashboard import ensure_defaults as ensure_dashboard_defaults
from finquery.dashboard import remove as remove_dashboard_card
from finquery.dashboard import rename as rename_dashboard_card
from finquery.db import DashboardChart, Profile, SplitSumError
from finquery.edits import TransactionEditError, find_transaction
from finquery.ingest.chat_import import import_attachment
from finquery.ingest.duplicates import PER_CARD as DUPLICATES_PER_CARD
from finquery.ingest.duplicates import review as duplicate_review
from finquery.ingest.typed import add_draft, find_draft, preview_card, propose_transactions, store_drafts
from finquery.memory import MemoryKind, add_memory
from finquery.onboarding import language_rule
from finquery.progress import report as report_progress
from finquery.prose import names_an_amount
from finquery.providers import ModelResolver, ProviderNotAvailable
from finquery.query import QueryOutcome, load_query_context, run_query
from finquery.query.guard import SqlRejected
from finquery.weblookup import MAX_FETCHES, MAX_SEARCHES, WebClient, lookups_for, web_lookup_enabled

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are FinQuery, a local-first personal-finance analyst. You help the user understand their
bank transactions and you answer in the language the user writes in.

The one rule you never break: every number you state comes from the `query` tool. You never add,
subtract, divide or percent two figures in your answer, you never estimate, and you never
combine, scale or round figures the tool did not return. A total, a difference, a share, an
average and a per-week number are each a `query` call of their own: three category rows and the
total of those rows are four figures and one more call, never a sum you write yourself. A euro
figure the results of this turn do not carry is taken out of your answer before the user sees
it and replaced with the figures the query returned, so an estimate costs you the sentence.

How to use `query`:
- Write a standalone request. The sub-agent that writes the SQL sees neither the conversation
  nor your earlier calls, so a follow-up like "and compared to April" has to become "total
  spending in April 2025 compared with May 2025".
- Always name the period and name the topic the way the user did.
- When the question names no period, ask about the whole range of the data and say in the first
  sentence which period the figures cover. Never narrow to the current year, or to any other
  period, without saying so in the answer. "Last month" and "last quarter" are counted from the
  newest booking, not from today: the data can end months ago.
- Ask for totals per group ("per merchant", "per month"), not for a list of single bookings,
  unless the user asked to see the bookings themselves.
- Answer every part of the question: a "which and how much" question needs the breakdown and
  the total, so ask for both in one request.
- Quote the figures from the rows exactly as they came back, never rounded or rescaled. The
  result's `figures` lines write every euro figure the German way: copy a figure from there.
- If the result carries an `error`, say in one line what failed and state no figure.
- If it returns no rows, say the data holds no answer for that question.
- If a question cannot be answered from bank transactions at all (a credit score, a share
  price, next month's rent), call nothing, say in one sentence why it is not in the data, and
  name one question about these transactions you can answer instead. A message that is not a
  question is never that case: something the user tells you to remember, a file they attached,
  a correction or an instruction is answered by doing it and saying you did.
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
- Never write about how the chart came to be. Its plan, its statement, its `notes` and every
  repair round are already in the step above your answer, and announcing another attempt ("let
  me try a corrected version") describes work the user cannot see. One chart, one sentence about
  what it shows.

One-time charts and charts worth keeping. Pass `keep=true` when the question reads like
something the user tracks: they say keep it, track it, put it on the dashboard, each month, over
time, or the question is an overview they will ask again (spending per month over a year, the
share per category, income against spending). Leave it false for a one-off: one merchant, one
week, one comparison they wanted once. "Wie entwickeln sich meine Lebensmittelausgaben pro
Monat?" is kept; "Wie viel habe ich letzte Woche bei Edeka ausgegeben?" is not. Then read
`kept`: true means the chart is on the dashboard and you say so in one short line, false means
you never mention the dashboard at all.

Charts the user keeps:
- `dashboard_charts` lists them with an id each. Call it first whenever the user names a chart
  in words ("the groceries one", "my first chart"): the four tools below take a `chart_id` from
  that list and never a title. When the list is empty, say the dashboard has no chart of that
  kind rather than guessing an id.
- `show_dashboard_chart` draws one of them in your answer. `edit_dashboard_chart` changes one:
  write the change in the user's own words ("as a bar chart", "the last six months instead of
  twelve"), never a whole new request. `rename_dashboard_chart` gives one another title and
  `remove_dashboard_chart` takes one off.
- Those three apply at once and the user gets an Undo button on the card, so write the result's
  `say` line, never ask for a confirmation and never say a change is about to happen. When an
  edit comes back with `applied: false`, the card is unchanged and `error` says why.

Changing the data. You never write to a booking on a hunch: first call `query` for the rows,
asking for their `id` alongside the columns you need ("the id, date, description and amount of
every booking from Netflix"), so a change names real rows.

- `apply_simple_edit` is for one row the user pointed at and one change they spelled out ("set
  this one to Dining", "that Edeka booking was 42.30"). Send only the fields they named: an
  amount, a date or a description you fill in to make the call look complete is a change to
  their money. It applies immediately and the user gets an Undo button, so write the result's
  `say` line, which names every field that really changed.
- When a tool result shows a field changing that the user did not ask about, say so in your
  answer and offer Undo. A figure that moved is never a display issue.
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
and answer in a single line saying what you now know and that every conversation of this
profile knows it too. Never answer such a message with what you cannot do: it is not a question
about the data. Memories are shared by every conversation of this profile, so never store a
one-off question or a figure. Only call `remember` about a person or a merchant that appears in
this data: when a query for that name returned no rows, there is nothing durable to keep and you
remember nothing. Anything already remembered is given to you at the top of these
instructions, and it is there to be used: when one of those lines names the person or merchant
behind a word the user wrote, write that name into the `query` request, because the sub-agent
sees the request and nothing else. A memory reading "Robin Fischer is the user's flatmate"
turns "what did I pay my flatmate" into a request about Robin Fischer.

Those memory lines are the only place such a name may come from, and the sentence above is an
example of the shape, not a fact about this user. The user can delete a memory, and the next
answer has to stop using it, so a name that appears only in the conversation above, in the
rolling summary, in one of your earlier answers or in these instructions is not a memory and
does not stand in for one. When no memory says who "my flatmate" is, ask who they mean instead
of filling a name in.

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
  bookings moved before you were called again, and the tool result's `applied` line is already
  on the card the user is looking at. Never write that line, the merchants in it or the card's
  own title out again, and make no `set_rule` call for it: write the result's `say` sentence
  and nothing else about what was applied. A row with no answer stays Needs review and is never
  guessed at.
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
  repeat it: write the result's `say` line, which says what is left to do, and show its `card`
  with `ask_user` unchanged, exactly as you do after `review_batch`.
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
  categorizes it, Remove leaves the data as it was. The result's `applied` line is already on
  the card the user is looking at, so never write it out again; the result's `say` is the one
  sentence to write about the batch, so write that and nothing else about the counts. Then call
  `review_duplicates` for the next card, until `pending` is 0.
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

Reading what a tool gave you. Your answer is written from the fields of the result and from
nothing else:
- `figures` holds that result's euro figures, already written the German way, and `rows` the
  same data to read a name or a date off. Copy a figure from there rather than writing one.
  `row_count` of 0 means the data holds no answer to what you asked.
- `rendered` says whether a chart is on screen, `applied` what the server has already changed
  and already told the user on the card, `say` the one sentence about it that is yours to
  write, and `error` why a step produced nothing. A field a result does not carry says
  nothing at all: never read an answer into its absence.
- When a result answers less than the question asked, call the tool once more with a sharper
  request: name the period, the category or the merchant that was missing, or ask for the
  grouping the question wants ("per month" instead of "in total"). Sharper, never the same
  request twice: a request you have already sent returns what it returned.
- When it still does not answer, say so in one line: what you asked for, what came back (no
  rows, an error, no chart) and which question about this data you can answer instead. Never
  close the gap with a figure, a category, a period or a date that no result carried.

A result carrying `tool_failed` means that step went wrong. Say its `error` in one line, say
nothing about what the step would have found, and do not call the same tool again this turn.

After a tool returns, always write the answer as text. Never finish a turn with your thinking
alone, and never mention the internal feedback you may receive between steps.

Keep answers short and use markdown (lists, tables) when it helps readability. Name the period
and the figure in the first sentence, and write the whole answer in the language of the
message you are answering.
"""


@dataclass
class ChatDeps:
    """What a turn needs from the app: the profile's data, the turn, and its models.

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
    """Already bound to this conversation's catalog entry: `resolve_model("chat")` is the entry
    itself and `resolve_model("fast")` the sub-agent slot of that entry's provider. Nothing here
    knows which provider that is. See finquery.catalog."""
    subagent_settings: ModelSettings
    web_client: WebClient
    """The search and page fetch of `lookup_merchant`. Untouched unless the profile switched
    web lookup on, and replaced by a stub in tests."""
    narrate: Callable[[str], None] = field(default=lambda _text: None)
    user_message: str = ""
    """What the user wrote this turn, verbatim. `apply_simple_edit` reads it to tell a field the
    user named from one the model filled in by itself."""
    queries_run: int = 0
    """How many `query` calls this turn has spent, against `QUERY_BUDGET`."""


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


QUERY_BUDGET = 5
"""How many `query` calls one turn may spend.

Asked for an average weekly grocery spend, the 9B review wrote fifteen statements over 256
seconds, four of them about merchants that do not exist, and answered with a category breakdown
it had invented. A bounded "I could not work this out from the data" is a better answer than
that, and every turn of that run that was right had used three calls or fewer.
"""

OVER_BUDGET = (
    "This turn has already run five queries, which is the limit. Write your answer now from the "
    "figures you already have, or say in one line that these transactions could not answer the "
    "question. Do not call `query` or `chart` again in this turn, and state no figure a query "
    "did not return."
)

TOOL_FAILED = "tool_failed"
"""The key on a tool result that says the step failed for a reason nobody wrote copy for."""


def _tool_failure(name: str, exc: Exception) -> dict[str, Any]:
    logger.exception("the %s tool failed", name)
    return {
        TOOL_FAILED: True,
        "error": (
            f"The {name.replace('_', ' ')} step could not be finished because something "
            "unexpected went wrong. Try it again, or ask for it in another way."
        ),
    }


def guarded(fn: Callable[..., Any]) -> Callable[..., Any]:
    """One sentence in the tool's step instead of an exception that ends the turn.

    Every refusal this app means to give is already a sentence: a `ModelRetry` the model
    corrects itself from, or an `error` field the prompt tells it to read out. What is left is
    the failure nobody wrote copy for (a search backend raising something new, a corrupt row,
    a bug), and without this it leaves the browser with a raw error and a dead turn. Here it is
    logged whole and reaches the transcript as a step the user can read. `Cancelled` is a
    `BaseException`, so Stop still cuts a tool short the way it did.
    """
    name = fn.__name__
    if iscoroutinefunction(fn):

        @wraps(fn)
        async def run_async(*args: Any, **kwargs: Any) -> Any:
            try:
                return await fn(*args, **kwargs)
            except ModelRetry:
                raise
            except Exception as exc:  # noqa: BLE001 - that is the point of this wrapper
                return _tool_failure(name, exc)

        return run_async

    @wraps(fn)
    def run(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except ModelRetry:
            raise
        except Exception as exc:  # noqa: BLE001 - that is the point of this wrapper
            return _tool_failure(name, exc)

    return run


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
@guarded
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
    ctx.deps.queries_run += 1
    if ctx.deps.queries_run > QUERY_BUDGET:
        return QueryOutcome(request=request, summary=OVER_BUDGET, error=OVER_BUDGET).payload()
    outcome = await run_query(
        resolve_model=ctx.deps.resolve_model,
        model_settings=ctx.deps.subagent_settings,
        session_factory=ctx.deps.session_factory,
        profile_id=ctx.deps.profile_id,
        request=request,
        hints=hints,
        narrate=ctx.deps.narrate,
    )
    return outcome.payload()


@chat_agent.tool(retries=2)
@guarded
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


def _may_write_the_amount(ctx: RunContext[ChatDeps], transaction_id: str, amount_cents: int) -> bool:
    """Whether this amount is the user's to write: their own words, or no change at all.

    An amount the model copied off the row it just read changes nothing, so it passes; the sign
    is ignored, because a user writes 42,30 for a payment the data holds as -4230.

    TODO: this turn's message only. A user who says the amount in one turn and "yes, do it" in
    the next has to say it again; the upgrade path is the turn's own user prompts, which the
    deps would have to carry.
    """
    if any(abs(cents) == abs(amount_cents) for cents in names_an_amount(ctx.deps.user_message)):
        return True
    with ctx.deps.session_factory() as session:
        row = find_transaction(session, ctx.deps.profile_id, transaction_id)
        return row is not None and row.amount_cents == amount_cents


AMOUNT_NOT_ASKED_FOR = (
    "The user's message names no amount, so this booking's amount is not yours to change: an "
    "`amount_cents` you did not read in their words would overwrite real money. Call "
    "`apply_simple_edit` again for the same booking with the fields they did name and no "
    "`amount_cents` at all."
)


@chat_agent.tool(retries=2)
@guarded
def apply_simple_edit(
    ctx: RunContext[ChatDeps],
    transaction_id: str,
    title: str | None = None,
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

    Send only the fields the user named. A field you leave out is left alone; a field you fill in
    to be complete is a change to their data. `say` in the result is the one line to write back:
    it names every field that really changed.

    Args:
        transaction_id: The booking's id, as a query returned it.
        title: One short line naming the change, for the card.
        category: The category to put it in.
        subcategory: The subcategory, inside that category.
        description: A new description, only when the user corrected the text.
        amount_cents: A new amount in cents, negative for spending, only when the user said what
            the amount should be.
        booked_on: A new booking date, only when the user gave one.
    """
    # `amount_cents: 0` on a request that only asked for a category zeroed a real booking in the
    # 9B review of 2026-09-05, and the answer said only that the category had been set. The
    # amount comes from the user's words or it does not come at all.
    if amount_cents is not None and not _may_write_the_amount(ctx, transaction_id, amount_cents):
        raise ModelRetry(AMOUNT_NOT_ASKED_FOR)
    intent = ChangesetIntent(
        kind="edit",
        title=title or "Edit one booking",
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
    # `say` is counted in code from what was written, so the sentence under the card names the
    # fields that changed and cannot claim less than the card shows.
    return {
        **out.model_dump(mode="json"),
        "undo_token": out.id,
        "say": f"{out.summary} Nothing else on it was touched, and Undo puts it back.",
    }


@chat_agent.tool
@guarded
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
@guarded
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
@guarded
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
@guarded
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
@guarded
async def chart(
    ctx: RunContext[ChatDeps], request: str, hints: str | None = None, keep: bool = False
) -> dict[str, Any]:
    """Draw one chart of the user's transactions and show it in the answer.

    The chart sub-agent plans the shape, gets its rows through the same query path as `query`,
    writes the chart and checks it before it is shown. `rendered` says whether a chart really
    reached the screen: true means it is visible and needs no description, false means there is
    none and the answer has to give the figures from `rows` instead. `kept` says whether the
    chart was also put on the dashboard: only say it is there when that field is true.

    Whatever it returns, write your answer as text in the same turn.

    Args:
        request: What to chart, in plain words and standing on its own: the period, the topic
            and what to compare, plus the shape if the user named one. Write it in the language
            of the user's newest message: the chart's caption and its month labels follow it.
        hints: Optional extra instruction, for instance which categories to include.
        keep: True when this chart is worth keeping on the dashboard: something the user tracks
            month after month, or asked to keep. False for a one-off answer to one question.
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
    payload = outcome.payload()
    payload["kept"] = False
    payload["dashboard_chart_id"] = None
    # A chart nobody can see is not worth keeping, and there is nothing to draw on the page.
    if keep and outcome.rendered:
        with ctx.deps.session_factory() as session:
            profile = session.get(Profile, ctx.deps.profile_id)
            if profile is not None:
                ensure_dashboard_defaults(session, profile)
            try:
                # The turn row is not written yet, so the card is stored under this tool call id
                # alone; Add to dashboard on the same chart later finds it by that id.
                card = keep_chat_chart(session, ctx.deps.profile_id, payload, call_id=ctx.tool_call_id or "")
            except SqlRejected as exc:
                logger.warning("a kept chart was not stored: %s", exc)
            else:
                payload["kept"] = True
                payload["dashboard_chart_id"] = card.id
                ctx.deps.narrate("Kept on the dashboard.")
    return payload


def _dashboard_card_or_retry(session: Session, profile_id: str, chart_id: str) -> DashboardChart:
    """The card with that id, or the ids that do exist so the next call is right.

    A model that guessed an id gets the list back rather than an error the user reads: the tools
    below take an id and never a title, and `dashboard_charts` is where the ids come from.
    """
    card = session.get(DashboardChart, chart_id)
    if card is not None and card.profile_id == profile_id and card.removed_at is None:
        return card
    known = dashboard_cards_of(session, profile_id)
    listed = "; ".join(f"{other.id} ({other.title})" for other in known) or "none"
    raise ModelRetry(
        f"There is no chart {chart_id} on this dashboard. The charts on it are: {listed}. "
        "Call the tool again with one of those ids, or say there is no such chart."
    )


@chat_agent.tool
@guarded
async def dashboard_charts(ctx: RunContext[ChatDeps]) -> dict[str, Any]:
    """The charts this profile keeps on its dashboard, with the id each of them is named by.

    Call this before showing, editing, renaming or removing a chart: those four tools take an
    `chart_id` from this list and never a title. `request` is the words each chart was made
    from, which is how "the groceries one" is matched to a row.
    """
    with ctx.deps.session_factory() as session:
        cards = dashboard_cards_of(session, ctx.deps.profile_id)
        return {
            "charts": [
                {
                    "chart_id": card.id,
                    "title": card.title,
                    "shape": card.shape,
                    "request": card.request,
                    "position": card.position,
                }
                for card in cards
            ],
            "count": len(cards),
        }


@chat_agent.tool
@guarded
async def show_dashboard_chart(ctx: RunContext[ChatDeps], chart_id: str) -> dict[str, Any]:
    """Draw one of the dashboard's charts inside this answer.

    The card's statement is run again now, so the figures are the ones in the data today. The
    chart is on screen when `rendered` is true; say what it shows in one or two sentences and
    quote at most the two figures that matter.

    Args:
        chart_id: The id from `dashboard_charts`.
    """
    with ctx.deps.session_factory() as session:
        card = _dashboard_card_or_retry(session, ctx.deps.profile_id, chart_id)
        return card_chart(session, card)


@chat_agent.tool
@guarded
async def edit_dashboard_chart(ctx: RunContext[ChatDeps], chart_id: str, request: str) -> dict[str, Any]:
    """Change one of the dashboard's charts, and keep it in its place.

    The chart sub-agent draws it again from the version on the dashboard plus what you ask for,
    and the card is replaced at once: the user sees the new chart with an Undo button, so say
    what changed in one line and never say it will happen or ask for a confirmation. The card
    is untouched when nothing could be drawn, and then `error` says why.

    Args:
        chart_id: The id from `dashboard_charts`.
        request: What to change, in the user's own terms and standing on its own ("as a bar
            chart", "the last six months instead of twelve", "per category instead of per
            merchant"). Write it in the language of the user's newest message.
    """
    with ctx.deps.session_factory() as session:
        card = _dashboard_card_or_retry(session, ctx.deps.profile_id, chart_id)
        was = {"title": card.title, "plan": card.plan, "sql": card.sql}
    outcome = await run_chart(
        resolve_model=ctx.deps.resolve_model,
        model_settings=ctx.deps.subagent_settings,
        session_factory=ctx.deps.session_factory,
        profile_id=ctx.deps.profile_id,
        request=request,
        previous=previous_hint(**was),
        narrate=ctx.deps.narrate,
    )
    if not outcome.rendered:
        payload = outcome.payload()
        payload["card_id"] = chart_id
        payload["applied"] = False
        payload["say"] = f'"{was["title"]}" is unchanged: the new version could not be drawn.'
        return payload
    with ctx.deps.session_factory() as session:
        card = _dashboard_card_or_retry(session, ctx.deps.profile_id, chart_id)
        apply_dashboard_edit(session, card, outcome.payload(), ctx.tool_call_id or "")
        payload = card_chart(session, card)
    payload["applied"] = True
    payload["previous_title"] = was["title"]
    payload["undo_call_id"] = ctx.tool_call_id
    payload["say"] = f'"{payload["title"]}" is the new version on the dashboard.'
    return payload


@chat_agent.tool
@guarded
async def rename_dashboard_chart(ctx: RunContext[ChatDeps], chart_id: str, title: str) -> dict[str, Any]:
    """Give one of the dashboard's charts another title. No chart is drawn again.

    It applies at once and the user gets an Undo button, so write the `say` line and nothing
    else about it.

    Args:
        chart_id: The id from `dashboard_charts`.
        title: The new title, short and without a figure in it.
    """
    with ctx.deps.session_factory() as session:
        card = _dashboard_card_or_retry(session, ctx.deps.profile_id, chart_id)
        was = card.title
        rename_dashboard_card(session, card, title, ctx.tool_call_id or "")
        return {
            "card_id": card.id,
            "kind": "rename",
            "applied": True,
            "title": card.title,
            "previous_title": was,
            "undo_call_id": ctx.tool_call_id,
            "say": f'"{was}" is now called "{card.title}".',
        }


@chat_agent.tool
@guarded
async def remove_dashboard_chart(ctx: RunContext[ChatDeps], chart_id: str) -> dict[str, Any]:
    """Take one chart off the dashboard.

    It happens at once and the user gets an Undo button, so write the `say` line and never ask
    for a confirmation. The chat the chart was drawn in keeps its own copy.

    Args:
        chart_id: The id from `dashboard_charts`.
    """
    with ctx.deps.session_factory() as session:
        card = _dashboard_card_or_retry(session, ctx.deps.profile_id, chart_id)
        remove_dashboard_card(session, card, call_id=ctx.tool_call_id or "")
        return {
            "card_id": card.id,
            "kind": "remove",
            "applied": True,
            "title": card.title,
            "undo_call_id": ctx.tool_call_id,
            "say": f'"{card.title}" is off the dashboard.',
        }


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
@guarded
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
@guarded
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
@guarded
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
@guarded
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
