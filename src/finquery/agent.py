"""The chat agent: the model the user talks to, and the tools it may call.

The model is chosen per run from the conversation's slot. Tools get what they need from
`ChatDeps`, so the agent itself holds no application state. Each tool that needs a model
resolves its own slot through the deps; later tickets add chart, import_file and
propose_changeset the same way.

`ask_user` is the odd one out: it has no function, because a human answers it in the browser.
See `finquery.ask_user` and ADR 0007.
"""

from dataclasses import dataclass
from typing import Any

from pydantic_ai import Agent, RunContext
from pydantic_ai.settings import ModelSettings
from pydantic_ai.tools import DeferredToolRequests
from sqlalchemy.orm import Session, sessionmaker

from finquery.ask_user import ask_user_toolset
from finquery.categorize import QUESTIONS_PER_CARD, pending_questions
from finquery.categorize import set_rule as store_category_rule
from finquery.categorize import split_choice
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

Categories and rules:
- A booking with no category is `Needs review`. `Unknown` is a category only the user assigns,
  never you.
- A category rule is the user's own pattern to category mapping and the highest-priority
  categorization stage. `set_rule` stores one and immediately recategorizes every booking of
  that merchant in the profile.
- When the user states a rule in plain words ("PayPal to Anna is always Dining", "Rewe ist
  immer Lebensmittel"), call `set_rule` and then confirm in one line with the figures it
  returned. Never say a rule was stored without calling the tool.
- The pattern is the merchant as it appears in the booking text ("Anna Weber", "REWE"), never a
  whole sentence and never a booking id.
- `review_batch` returns the merchants that still need the user's decision, each with a guess
  and ready-made buttons. Hand those rows straight to `ask_user` as a Question card.
- When a Question card comes back answered, call `set_rule` once per answer, with the row's
  `ref` as the pattern and the answer's `value` as the category ("Groceries > Supermarket" is a
  category and its subcategory; free text is a category name you resolve to one of the
  profile's categories). A row with no answer stays Needs review and is never guessed at.
- After the rules are stored, call `review_batch` again and ask the next card, until nothing is
  pending or the user asks you to stop. When nothing is pending, say so in one line.

Keep answers short and use markdown (lists, tables) when it helps readability. Name the period
and the figure in the first sentence.
"""


@dataclass
class ChatDeps:
    """What a turn needs from the app: the profile's data and the model slots.

    `subagent_settings` is what every sub-agent a tool starts runs with (reasoning off on
    OpenRouter), so a tool never has to know provider specifics.
    """

    session_factory: sessionmaker[Session]
    profile_id: str
    resolve_model: ModelResolver
    subagent_settings: ModelSettings


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
    elif context.categorized_count < context.transaction_count:
        lines.append(
            f"{context.transaction_count - context.categorized_count} bookings are still Needs review. "
            "`review_batch` is how you ask about them."
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
    """The merchants that still need the user's decision, ready to become a Question card.

    Each row carries the merchant pattern to use as an `ask_user` ref, a sample booking, how
    many bookings it stands for, a guess from the categorizer and the buttons to offer. Call
    `ask_user` with these rows; do not ask about a merchant this did not return.

    Args:
        limit: How many merchants to ask about at once, at most five.
    """
    with ctx.deps.session_factory() as session:
        questions, pending = await pending_questions(
            session,
            ctx.deps.profile_id,
            resolve_model=ctx.deps.resolve_model,
            model_settings=ctx.deps.subagent_settings,
            limit=max(1, min(limit, QUESTIONS_PER_CARD)),
        )
    return {
        "pending_merchants": pending,
        "questions": [question.payload() for question in questions],
    }
