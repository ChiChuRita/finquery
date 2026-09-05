"""The query checks itself: the degenerate rules, the check pass and the one rewrite.

Ticket 40. Every test drives the chat endpoint: the chat model calls `query` and reports what
came back, the sub-agent behind it is scripted with one statement per attempt, and the check
pass is scripted with one verdict per call. What is asserted is which statement executed, how
many model calls it took and what the thinking panel said.
"""

import httpx

from finquery.query.check import ALL_NULL, CHECKING, KEPT, NO_ROWS, SINGLE_ZERO

from .conftest import Chat, Scripts, new_conversation
from .test_chart import narration
from .test_query import answer, ask_query_then_report, import_synthetic, scripted_sql, tool_output

# A statement whose figure is right, and three that answer nothing.
REWE_SPENDING = (
    "SELECT ROUND(-SUM(amount), 2) AS total_eur FROM transaction_view WHERE amount < 0 "
    "AND lower(description || ' ' || coalesce(counterparty, '')) LIKE '%rewe%'"
)
MAY_ONLY = (
    "SELECT ROUND(-SUM(amount), 2) AS total_eur FROM transaction_view WHERE amount < 0 "
    "AND booked_on BETWEEN '2025-05-01' AND '2025-05-31'"
)
WHOLE_YEAR = "SELECT ROUND(-SUM(amount), 2) AS total_eur FROM transaction_view WHERE amount < 0"
NO_SUCH_YEAR = (
    "SELECT booked_on AS day, ROUND(-SUM(amount), 2) AS total_eur FROM transaction_view "
    "WHERE booked_on BETWEEN '2019-01-01' AND '2019-12-31' GROUP BY day"
)
MISSPELLED = (
    "SELECT ROUND(-SUM(amount), 2) AS total_eur FROM transaction_view WHERE amount < 0 "
    "AND lower(description || ' ' || coalesce(counterparty, '')) LIKE '%rewf%'"
)
WRONG_SIGN = (
    "SELECT ROUND(COALESCE(SUM(amount), 0), 2) AS total_eur FROM transaction_view WHERE amount > 0 "
    "AND lower(description || ' ' || coalesce(counterparty, '')) LIKE '%rewe%'"
)

REVISE = {
    "verdict": "revise",
    "reason": "It totals May 2025 only, but the question names no period.",
    "intent": "Total spending over the whole range of the data.",
}


async def test_a_revise_verdict_makes_the_sub_agent_write_the_statement_that_runs(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """The failure the guard cannot see: valid SQL that answers a different question."""
    await import_synthetic(client, profile_id)
    respond = scripted_sql(MAY_ONLY, WHOLE_YEAR, checks=[REVISE])
    scripts.fast = ask_query_then_report("total spending")
    scripts.fast_call = respond  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "How much have I spent in total?")

    output = tool_output(chunks)
    # The second statement is the one that executed, and its figure is the one in the answer.
    assert "2025-05-01" not in output["sql"]
    assert output["rows"][0]["total_eur"] > 10000
    assert answer(chunks) == f"Result: total_eur={output['rows'][0]['total_eur']}"

    prompts, judgements = respond.prompts, respond.judgements  # type: ignore[attr-defined]
    assert len(prompts) == 2 and len(judgements) == 1
    # The rewrite carries the reason, the statement that earned it and what to ask instead.
    assert "did not answer the question" in prompts[1]
    assert REVISE["reason"] in prompts[1]
    assert f"Answer this instead: {REVISE['intent']}" in prompts[1]
    assert "2025-05-01" in prompts[1], "the previous statement goes back with the reason"
    # The check saw the question, the statement and the figure it returned, in euros.
    assert "Question: total spending" in judgements[0]
    assert "2025-05-01" in judgements[0]
    assert "total_eur" in judgements[0] and "EUR" in judgements[0]
    # Both steps are in the thinking panel, like the chart repairs.
    assert CHECKING in narration(chunks)
    assert f"Rewriting: {REVISE['reason']}" in narration(chunks)


async def test_an_ok_verdict_leaves_the_result_alone(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    await import_synthetic(client, profile_id)
    respond = scripted_sql(REWE_SPENDING, checks=[{"verdict": "ok"}])
    scripts.fast = ask_query_then_report("spending at REWE over the whole range")
    scripts.fast_call = respond  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "How much did I spend at REWE?")

    output = tool_output(chunks)
    assert output["error"] is None
    assert output["rows"][0]["total_eur"] > 0
    assert len(respond.prompts) == 1, "one statement, and no rewrite"  # type: ignore[attr-defined]
    assert len(respond.judgements) == 1  # type: ignore[attr-defined]
    assert CHECKING in narration(chunks)
    assert "Rewriting" not in narration(chunks)


async def test_each_degenerate_result_is_rewritten_once_before_a_model_judges_it(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """No rows, an empty figure and a zero on a merchant the data carries, one rewrite each.

    Costs nothing: the trigger is code, so the check pass never runs on a result this shape.
    """
    await import_synthetic(client, profile_id)
    for degenerate, reason in ((NO_SUCH_YEAR, NO_ROWS), (MISSPELLED, ALL_NULL), (WRONG_SIGN, SINGLE_ZERO)):
        respond = scripted_sql(degenerate, REWE_SPENDING)
        scripts.fast = ask_query_then_report("what I spent at REWE")
        scripts.fast_call = respond  # type: ignore[assignment]
        conversation_id = await new_conversation(client, profile_id)

        _, chunks = await chat(conversation_id, "Wie viel habe ich bei REWE ausgegeben?")

        output = tool_output(chunks)
        assert output["rows"][0]["total_eur"] > 0, degenerate
        prompts, judgements = respond.prompts, respond.judgements  # type: ignore[attr-defined]
        assert len(prompts) == 2, degenerate
        assert judgements == [], "a degenerate result is caught in code, not by a model"
        assert reason in prompts[1]
        assert "Look for the cause" in prompts[1] and "2025-01-01 to 2025-12-28" in prompts[1]
        assert f"Rewriting: {reason}" in narration(chunks)
        assert CHECKING not in narration(chunks)


async def test_a_zero_is_left_alone_when_the_question_names_nothing_the_data_carries(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """A figure of zero is an answer unless the question named something that should be there."""
    await import_synthetic(client, profile_id)
    nothing_moved = (
        "SELECT ROUND(COALESCE(SUM(amount), 0), 2) AS total_eur FROM transaction_view "
        "WHERE booked_on = '2019-05-01'"
    )
    respond = scripted_sql(nothing_moved)
    scripts.fast = ask_query_then_report("the net of everything booked on 1 May 2019")
    scripts.fast_call = respond  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "What moved on the first of May 2019?")

    assert tool_output(chunks)["rows"] == [{"total_eur": 0}]
    assert len(respond.prompts) == 1, "no rewrite: the zero is the answer"  # type: ignore[attr-defined]
    assert len(respond.judgements) == 1, "the check still judged it"  # type: ignore[attr-defined]


async def test_the_degenerate_retry_happens_at_most_once(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """A second empty result is the answer: the data holds none of it."""
    await import_synthetic(client, profile_id)
    respond = scripted_sql(MISSPELLED, MISSPELLED)
    scripts.fast = ask_query_then_report("what I spent at REWE")
    scripts.fast_call = respond  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "Wie viel habe ich bei REWE ausgegeben?")

    output = tool_output(chunks)
    assert output["rows"] == [{"total_eur": None}]
    assert output["error"] is None
    assert len(respond.prompts) == 2, "two statements, and no third"  # type: ignore[attr-defined]
    assert respond.judgements == []  # type: ignore[attr-defined]


async def test_a_query_costs_at_most_three_model_calls(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """The statement, the check, the rewrite. A rewrite is never checked or rewritten again."""
    await import_synthetic(client, profile_id)
    respond = scripted_sql(MAY_ONLY, MAY_ONLY, checks=[REVISE, REVISE])
    scripts.fast = ask_query_then_report("total spending")
    scripts.fast_call = respond  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "How much have I spent in total?")

    prompts, judgements = respond.prompts, respond.judgements  # type: ignore[attr-defined]
    assert len(prompts) + len(judgements) == 3
    assert len(prompts) == 2 and len(judgements) == 1
    assert tool_output(chunks)["error"] is None, "the rewritten statement is the result"


async def test_the_assistants_hint_is_judged_rather_than_trusted(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """A hint is the assistant's reading of the question, and that is often the mistake.

    Asked for the smallest recurring payment on 2026-09-05, the chat agent hinted "sortieren
    nach amount ascending", which is the largest, and the sub-agent did as it was told. So the
    hint goes to the check as what it is rather than switching the check off. The chart tool is
    the one caller whose intent really is pinned, and it says so with `pinned=True`; the chart
    tests fail if a check ever reaches their scripted model.
    """
    await import_synthetic(client, profile_id)
    respond = scripted_sql(MAY_ONLY)
    scripts.fast = ask_query_then_report("total spending", hints="Only May 2025, one figure.")
    scripts.fast_call = respond  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "How much did I spend in May?")

    assert tool_output(chunks)["error"] is None
    judgements = respond.judgements  # type: ignore[attr-defined]
    assert len(judgements) == 1
    assert "which is its reading and not the question:\nOnly May 2025, one figure." in judgements[0]
    assert CHECKING in narration(chunks)


async def test_the_check_is_skipped_when_the_statement_came_from_a_retry(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """A statement that already came back once has had its round."""
    await import_synthetic(client, profile_id)
    respond = scripted_sql("DELETE FROM transaction_view WHERE amount < 0", REWE_SPENDING)
    scripts.fast = ask_query_then_report("what I spent at REWE")
    scripts.fast_call = respond  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "Wie viel habe ich bei REWE ausgegeben?")

    assert tool_output(chunks)["rows"][0]["total_eur"] > 0
    assert len(respond.prompts) == 2, "the refusal went back, and the second statement stands"  # type: ignore[attr-defined]
    assert respond.judgements == []  # type: ignore[attr-defined]


READING = "period: May 2025. filter: none. sign: spending, amount < 0. grouping: one figure."


async def test_the_reading_the_sub_agent_wrote_travels_into_the_check_and_the_rewrite(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """A retry corrects a reading it can see, rather than starting from nothing (ticket 42)."""
    await import_synthetic(client, profile_id)
    respond = scripted_sql(MAY_ONLY, WHOLE_YEAR, reasonings=[READING], checks=[REVISE])
    scripts.fast = ask_query_then_report("total spending")
    scripts.fast_call = respond  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "How much have I spent in total?")

    prompts, judgements = respond.prompts, respond.judgements  # type: ignore[attr-defined]
    # The check saw how the statement was meant, which is where a misread period shows first.
    assert f"How the statement was meant:\n{READING}" in judgements[0]
    # The rewrite is a correction: its own reading, the statement, the finding, and what to hand back.
    assert f"Your reasoning was:\n{READING}" in prompts[1]
    assert "keep what was right and change only what the problem names" in prompts[1]
    assert "Answer with the corrected reasoning and the corrected statement." in prompts[1]
    assert tool_output(chunks)["rows"][0]["total_eur"] > 10000


async def test_a_refused_statement_goes_back_with_the_reading_that_wrote_it(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    await import_synthetic(client, profile_id)
    refused = "SELECT ROUND(-SUM(amount_cents), 2) AS total_eur FROM transaction_view WHERE amount < 0"
    respond = scripted_sql(refused, WHOLE_YEAR, reasonings=[READING])
    scripts.fast = ask_query_then_report("total spending")
    scripts.fast_call = respond  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "How much have I spent in total?")

    prompts = respond.prompts  # type: ignore[attr-defined]
    assert len(prompts) == 2
    assert f"Your reasoning was:\n{READING}" in prompts[1]
    assert "Refused SQL:" in prompts[1] and "amount_cents" in prompts[1]
    assert tool_output(chunks)["error"] is None


async def test_a_rewrite_that_answers_nothing_leaves_the_first_result_standing(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """A check on a 9B model asks for a rewrite it should not, so a rewrite has to earn it."""
    await import_synthetic(client, profile_id)
    respond = scripted_sql(MAY_ONLY, MISSPELLED, checks=[REVISE])
    scripts.fast = ask_query_then_report("total spending")
    scripts.fast_call = respond  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "How much have I spent in total?")

    output = tool_output(chunks)
    assert "2025-05-01" in output["sql"], "the first statement is the one that answered"
    assert output["rows"][0]["total_eur"] > 0
    assert len(respond.prompts) == 2, "the rewrite was written and then thrown away"  # type: ignore[attr-defined]
    assert KEPT in narration(chunks)
