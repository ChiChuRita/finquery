"""The chat agent: its system prompt, the deps one turn hands it, and its tools.

The model is chosen per run from the conversation's slot. Tools get what they need from
`ChatDeps`, so the agent itself holds no application state. `query`, `remember`, `set_rule`,
`review_batch`, `import_file`, `extract_transaction` and `add_transaction` are the tools; later
tickets add chart and propose_changeset the same way, and each one that needs a model resolves
its own slot through the deps.

`ask_user` is the odd one out: it has no function, because a human answers it in the browser.
See `finquery.ask_user` and ADR 0008.

Selected memories and the rolling summary arrive as run instructions assembled by
`finquery.context.assemble`, not from here.
"""

from dataclasses import dataclass
from functools import partial
from typing import Any

from pydantic_ai import Agent, RunContext
from pydantic_ai.settings import ModelSettings
from pydantic_ai.tools import DeferredToolRequests
from sqlalchemy.orm import Session, sessionmaker

from finquery import attachments
from finquery.ask_user import ask_user_toolset
from finquery.categorize import QUESTIONS_PER_CARD, pending_questions
from finquery.categorize import set_rule as store_category_rule
from finquery.categorize import split_choice
from finquery.ingest.chat_import import import_attachment
from finquery.ingest.typed import add_draft, find_draft, preview_card, propose_transactions, store_drafts
from finquery.memory import MemoryKind, add_memory
from finquery.progress import report as report_progress
from finquery.providers import ModelResolver, ProviderNotAvailable
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

When the user tells you something durable about their finances (what a merchant is, that
PayPal payments to Anna are dinner, which categories they care about), call `remember` once
with one short sentence and confirm it in a single line of your answer. Memories are shared by
every conversation of this profile, so never store a one-off question or a figure. Anything
already remembered is given to you at the top of these instructions.

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

Files the user attaches:
- `import_file` is what turns an attached file into transactions. Call it once per file, with
  the file name exactly as the list of attached files spells it, and pass `account_name` only
  when the user named an account.
- A CSV from a bank we recognize is imported straight away. For an unknown layout the tool comes
  back asking for the column mapping to be confirmed: show its `card` with `ask_user`
  unchanged, and when the user confirms, call `import_file` again for the same file with
  `confirmed=true`.
- When a file is imported the tool returns a `summary` counted in code and the merchants it
  could not place. Say the summary in one line, quoting its figures, and hand the `questions`
  straight to `ask_user` as a Question card, exactly as you do after `review_batch`.
- A PDF or a photo is stored but cannot be read yet. Pass the tool's `message` on as it is; it
  is not an error and there is nothing to retry.

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
            "tell the user the profile is empty and that a bank statement can be dropped into this "
            "chat or imported on the Import page."
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


@chat_agent.tool
async def import_file(
    ctx: RunContext[ChatDeps],
    file_name: str,
    account_name: str | None = None,
    confirmed: bool = False,
) -> dict[str, Any]:
    """Import a file the user attached to this conversation.

    Runs the same pipeline as the Import page: it reads the CSV, takes the preset of a bank we
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
async def add_transaction(ctx: RunContext[ChatDeps], ref: str) -> dict[str, Any]:
    """Write one transaction the user confirmed on a preview card, and categorize it.

    The booking is written from the stored draft, not from anything you pass here, so the ref is
    all it takes. Calling it twice for the same ref adds nothing.

    Args:
        ref: The `ref` of the confirmed row, for instance `t1`.
    """
    with ctx.deps.session_factory() as session:
        draft = find_draft(session, ctx.deps.conversation_id, ref)
        if draft is None:
            return {"status": "no_such_draft", "ref": ref, "error": f"No preview row called {ref!r}."}
        return await add_draft(
            session,
            ctx.deps.profile_id,
            draft,
            resolve_model=ctx.deps.resolve_model,
            model_settings=ctx.deps.subagent_settings,
        )
