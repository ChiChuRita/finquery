"""Categorization: rules, merchant enrichment, the categorizer sub-agent, and the review queue.

`pipeline` is the entry point for an import; `rules` is where a Question card answer or a
plain-language statement becomes a rule that recategorizes the profile.
"""

from finquery.categorize.pipeline import (
    QUESTIONS_PER_CARD,
    Question,
    Report,
    categorize_import,
    pending_questions,
    review_card,
)
from finquery.categorize.rules import RuleOutcome, set_rule, split_choice

__all__ = [
    "QUESTIONS_PER_CARD",
    "Question",
    "Report",
    "RuleOutcome",
    "categorize_import",
    "pending_questions",
    "review_card",
    "set_rule",
    "split_choice",
]
