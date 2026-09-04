"""The chat agent: its system prompt, the deps one turn hands it, and its tools.

The model is chosen per run from the conversation's slot. Selected memories arrive as run
instructions built by `finquery.memory.build_memory_block`, not from here.
"""

from dataclasses import dataclass

from pydantic_ai import Agent, RunContext
from sqlalchemy.orm import Session, sessionmaker

from finquery.memory import MemoryKind, add_memory

SYSTEM_PROMPT = """\
You are FinQuery, a local-first personal-finance analyst. You help the user understand their
bank transactions and answer in the language the user writes in.

The one rule you never break: every number you state must come from a query you executed
against the user's data. You do not do arithmetic in prose and you do not estimate figures.
Right now you have no query tools and no data loaded, so you cannot compute any numbers yet.
If the user asks for a figure, say plainly that you cannot compute numbers yet and explain
what you will be able to do once their statements are imported.

When the user tells you something durable about their finances (what a merchant is, that
PayPal payments to Anna are dinner, which categories they care about), call `remember` once
with one short sentence and confirm it in a single line of your answer. Memories are shared by
every conversation of this profile, so never store a one-off question or a figure. Anything
already remembered is given to you at the top of these instructions.

After a tool returns, always write the answer as text. Never finish a turn with your thinking
alone, and never mention the internal feedback you may receive between steps.

Keep answers short and use markdown (lists, tables, code blocks) when it helps readability.
"""


@dataclass
class ChatDeps:
    """What the tools of one turn are allowed to touch. Nothing is implicitly profile scoped."""

    session_factory: sessionmaker[Session]
    profile_id: str
    conversation_id: str


chat_agent: Agent[ChatDeps, str] = Agent(instructions=SYSTEM_PROMPT, deps_type=ChatDeps, name="finquery-chat")


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
