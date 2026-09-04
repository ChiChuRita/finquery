"""The chat agent: its system prompt, the deps one turn hands it, and its tools.

The model is chosen per run from the conversation's slot. Tools get what they need from
`ChatDeps`, so the agent itself holds no application state. `query` and `remember` are the
first two tools; later tickets add chart, import_file and ask_user the same way, and each one
that needs a model resolves its own slot through the deps.

`propose_changeset` and `apply_simple_edit` are the writing tools. Neither one decides anything
about the data: `finquery.changesets` resolves the intent, refuses what the data model refuses
(and that sentence goes back to the model as a retry), and the user applies through REST.

Selected memories arrive as run instructions built by `finquery.memory.build_memory_block`,
not from here.
"""

from dataclasses import dataclass
from datetime import date
from typing import Any

from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.settings import ModelSettings
from sqlalchemy.orm import Session, sessionmaker

from finquery.changesets import ChangesetError, ChangesetIntent, propose, to_out
from finquery.changesets import apply as apply_changeset
from finquery.db import SplitSumError
from finquery.edits import TransactionEditError
from finquery.memory import MemoryKind, add_memory
from finquery.providers import ModelResolver
from finquery.query import load_query_context, run_query

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
- Quote the figures from the rows exactly as they came back, as EUR with two decimals.
- If the result carries an `error`, say in one line what failed and state no figure.
- If it returns no rows, say the data holds no answer for that question.
- Never write SQL yourself and never show SQL in your answer: the transcript already shows the
  statement that ran.

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
- A split needs at least two legs in cents that add up to the booking exactly, negative for
  spending. If a tool refuses, read the sentence it gives you and correct the call once.
- Adding, renaming, merging or deleting a category or subcategory is `propose_changeset` with
  kind `taxonomy`.

When the user tells you something durable about their finances (what a merchant is, that
PayPal payments to Anna are dinner, which categories they care about), call `remember` once
with one short sentence and confirm it in a single line of your answer. Memories are shared by
every conversation of this profile, so never store a one-off question or a figure. Anything
already remembered is given to you at the top of these instructions.

After a tool returns, always write the answer as text. Never finish a turn with your thinking
alone, and never mention the internal feedback you may receive between steps.

Keep answers short and use markdown (lists, tables, code blocks) when it helps readability.
Name the period and the figure in the first sentence.
"""


@dataclass
class ChatDeps:
    """What a turn needs from the app: the profile's data, the turn, and the model slots.

    Nothing is implicitly profile scoped: a tool touches exactly what is on here.
    `subagent_settings` is what every sub-agent a tool starts runs with (reasoning off on
    OpenRouter), so a tool never has to know provider specifics.
    """

    session_factory: sessionmaker[Session]
    profile_id: str
    conversation_id: str
    resolve_model: ModelResolver
    subagent_settings: ModelSettings


chat_agent: Agent[ChatDeps, str] = Agent(instructions=SYSTEM_PROMPT, deps_type=ChatDeps, name="finquery-chat")


@chat_agent.instructions
def data_brief(ctx: RunContext[ChatDeps]) -> str:
    """What the profile holds right now, so a question can be judged before it is queried."""
    with ctx.deps.session_factory() as session:
        context = load_query_context(session, ctx.deps.profile_id)
    if context.transaction_count == 0:
        return (
            "This profile has no transactions yet. Do not call `query` and do not state any number: "
            "tell the user the profile is empty and that a bank statement can be imported on the "
            "Import page."
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
    return "\n".join(lines)


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
