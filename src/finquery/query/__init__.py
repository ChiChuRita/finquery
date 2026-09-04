"""Asking the data a question.

`runner.run_query` is the whole path: the query sub-agent writes SQL on the fast slot, the
guard admits a single read-only SELECT over the profile's slice of `transaction_view`, and the
rows come back with the statement that produced them. The chat agent's `query` tool is a thin
wrapper around it, and ticket 06's chart sub-agent reuses the same call for its data.
"""

from finquery.query.guard import MAX_ROWS, Rows, SqlFailed, SqlRejected, execute_read_only, validate_sql
from finquery.query.runner import NO_DATA, QueryOutcome, run_query
from finquery.query.subagent import QueryContext, load_query_context, profile_facts, query_prompt, write_sql

__all__ = [
    "MAX_ROWS",
    "NO_DATA",
    "QueryContext",
    "QueryOutcome",
    "Rows",
    "SqlFailed",
    "SqlRejected",
    "execute_read_only",
    "load_query_context",
    "profile_facts",
    "query_prompt",
    "run_query",
    "validate_sql",
    "write_sql",
]
