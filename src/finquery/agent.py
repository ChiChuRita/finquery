"""The chat agent: the model the user talks to, and the tools it may call.

The model is chosen per run from the conversation's slot. Tools get what they need from
`ChatDeps`, so the agent itself holds no application state. `query` is the first tool; later
tickets add chart, import_file, ask_user, propose_changeset and friends the same way, and each
one that needs a model resolves its own slot through the deps.
"""

from dataclasses import dataclass
from typing import Any

from pydantic_ai import Agent, RunContext
from sqlalchemy.orm import Session, sessionmaker

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

Keep answers short and use markdown (lists, tables) when it helps readability. Name the period
and the figure in the first sentence.
"""


@dataclass
class ChatDeps:
    """What a turn needs from the app: the profile's data and the model slots."""

    session_factory: sessionmaker[Session]
    profile_id: str
    resolve_model: ModelResolver


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
    lines = [
        f"Today is {context.today.isoformat()}. The profile holds {context.transaction_count} bookings from "
        f"{context.first_booked_on} to {context.last_booked_on} in {', '.join(context.accounts)}.",
        f"Categories: {', '.join(name for name, _ in context.taxonomy)}.",
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
        session_factory=ctx.deps.session_factory,
        profile_id=ctx.deps.profile_id,
        request=request,
        hints=hints,
    )
    return outcome.payload()
