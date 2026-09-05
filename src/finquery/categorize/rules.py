"""Category rules: the profile's own patterns, and the code that applies them.

A rule is the highest-priority categorization stage and the thing a Question card answer or a
plain-language statement in chat turns into, so this module is where the rule stage of the
pipeline, the `set_rule` tool and the answers to a Question card all meet.

Matching goes through `merchants.fold`, the same normalization the dictionary uses: a rule
written `PayPal to Anna` never matches, a rule written `Anna Weber` matches
`PP.4711.PP . ANNA WEBER, Ihre Zahlung`. The tools tell the model to use the merchant token.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from finquery.ask_user import Applied, AskAnswer, AskRow
from finquery.categorize.merchants import contains, fold, merchant_of
from finquery.db import Category, CategoryRule, Subcategory, Transaction

TITLE_LENGTH = 120
DESCRIPTION_LENGTH = 200


@dataclass(frozen=True)
class Placement:
    """A resolved point in the taxonomy: a real category and an optional real subcategory."""

    category: Category
    subcategory: Subcategory | None = None

    @property
    def label(self) -> str:
        return f"{self.category.name} > {self.subcategory.name}" if self.subcategory else self.category.name


def load_categories(session: Session, profile_id: str) -> list[Category]:
    return list(
        session.scalars(
            select(Category)
            .options(selectinload(Category.subcategories))
            .where(Category.profile_id == profile_id)
            .order_by(Category.position)
        ).all()
    )


def taxonomy_of(categories: list[Category]) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """The shape the categorizer prompt wants."""
    return tuple((c.name, tuple(sub.name for sub in c.subcategories)) for c in categories)


def split_choice(choice: str) -> tuple[str, str | None]:
    """`Groceries > Supermarket` becomes `("Groceries", "Supermarket")`.

    Question cards and the `set_rule` tool both accept the combined form, because that is what
    a single button on a card has to carry.
    """
    for separator in (">", "/", "|"):
        if separator in choice:
            head, _, tail = choice.partition(separator)
            return head.strip(), tail.strip() or None
    return choice.strip(), None


def resolve(categories: list[Category], category: str, subcategory: str | None = None) -> Placement | None:
    """Find a category by name, case and spacing insensitive. Returns None when it is not one."""
    wanted = fold(category)
    found = next((c for c in categories if fold(c.name) == wanted), None)
    if found is None:
        return None
    if not subcategory:
        return Placement(category=found)
    sub_wanted = fold(subcategory)
    sub = next((s for s in found.subcategories if fold(s.name) == sub_wanted), None)
    return Placement(category=found, subcategory=sub)


def load_rules(session: Session, profile_id: str) -> list[CategoryRule]:
    """The profile's rules, most specific first: a longer pattern wins over a shorter one."""
    rules = list(session.scalars(select(CategoryRule).where(CategoryRule.profile_id == profile_id)).all())
    return sorted(rules, key=lambda rule: (-len(rule.pattern), rule.created_at), reverse=False)


def matching_rule(rules: list[CategoryRule], description: str, counterparty: str | None) -> CategoryRule | None:
    """The first rule whose pattern appears in this booking's description or counterparty."""
    folded = f"{fold(description)} {fold(counterparty)}".strip()
    return next((rule for rule in rules if contains(folded, rule.pattern)), None)


def enrich_row(row: Transaction, title: str, description: str | None) -> None:
    """Every row carries a friendly title and a short description, categorized or not."""
    row.enriched_title = title[:TITLE_LENGTH]
    row.enriched_description = description[:DESCRIPTION_LENGTH] if description else None


def place_row(row: Transaction, placement: Placement) -> None:
    row.category_id = placement.category.id
    row.subcategory_id = placement.subcategory.id if placement.subcategory else None


@dataclass
class RuleOutcome:
    """What a rule did: where it points, how many rows moved, and what went wrong."""

    pattern: str
    placement: Placement | None = None
    matched: int = 0
    updated: int = 0
    created: bool = False
    error: str | None = None
    sample: list[str] = field(default_factory=list)

    def payload(self) -> dict[str, object]:
        """The tool result: one line the assistant can confirm with, and the numbers behind it."""
        if self.error:
            return {"pattern": self.pattern, "error": self.error}
        assert self.placement is not None
        return {
            "pattern": self.pattern,
            "category": self.placement.category.name,
            "subcategory": self.placement.subcategory.name if self.placement.subcategory else None,
            "matched": self.matched,
            "updated": self.updated,
            "rule": "created" if self.created else "updated",
            "sample": self.sample,
            "error": None,
        }


SAMPLE_ROWS = 3

BULK_WORDS = frozenset(
    {
        "all",
        "alle",
        "allen",
        "every",
        "jede",
        "jeden",
        "row",
        "rows",
        "booking",
        "bookings",
        "buchung",
        "buchungen",
        "transaction",
        "transactions",
        "transaktion",
        "transaktionen",
    }
)
"""Words that make a pattern the request rather than a merchant.

"all Netflix rows" is a bulk change: it belongs in a changeset the user sees before it moves,
not in a rule that rewrites the rows at once (review of 2026-09-04). A single word is never
refused, so a merchant that happens to be one of these still works.
"""


def bulk_phrase(pattern: str) -> bool:
    words = fold(pattern).split()
    return len(words) > 1 and any(word in BULK_WORDS for word in words)


def set_rule(
    session: Session,
    profile_id: str,
    *,
    pattern: str,
    category: str,
    subcategory: str | None = None,
) -> RuleOutcome:
    """Store a rule and apply it to every matching booking in the profile.

    A rule is authoritative: it also recategorizes rows an earlier stage already placed, which
    is what makes "PayPal to Anna is always Dining" fix a wrong guess. Rows the rule touches
    also get their enrichment when they have none yet.
    """
    pattern = " ".join(pattern.split())
    if len(fold(pattern)) < 2:
        return RuleOutcome(pattern=pattern, error="A rule needs a merchant pattern of at least two characters.")
    if bulk_phrase(pattern):
        return RuleOutcome(
            pattern=pattern,
            error=(
                f"'{pattern}' is a request, not a merchant. Moving bookings that already exist is a "
                "bulk change: propose it with `propose_changeset` so the user sees the rows first. "
                "A rule takes the merchant on its own, for instance 'Netflix'."
            ),
        )
    categories = load_categories(session, profile_id)
    placement = resolve(categories, category, subcategory)
    if placement is None:
        names = ", ".join(c.name for c in categories)
        return RuleOutcome(pattern=pattern, error=f"'{category}' is not a category of this profile. Pick one of: {names}")

    existing = next(
        (
            rule
            for rule in load_rules(session, profile_id)
            if fold(rule.pattern) == fold(pattern)
        ),
        None,
    )
    if existing is None:
        session.add(
            CategoryRule(
                profile_id=profile_id,
                pattern=pattern,
                category_id=placement.category.id,
                subcategory_id=placement.subcategory.id if placement.subcategory else None,
            )
        )
    else:
        existing.category_id = placement.category.id
        existing.subcategory_id = placement.subcategory.id if placement.subcategory else None

    outcome = RuleOutcome(pattern=pattern, placement=placement, created=existing is None)
    for row in session.scalars(select(Transaction).where(Transaction.profile_id == profile_id)).all():
        if not contains(f"{fold(row.description)} {fold(row.counterparty)}".strip(), pattern):
            continue
        outcome.matched += 1
        if len(outcome.sample) < SAMPLE_ROWS:
            outcome.sample.append(row.enriched_title or row.description)
        already = row.category_id == placement.category.id and row.subcategory_id == (
            placement.subcategory.id if placement.subcategory else None
        )
        if not already:
            place_row(row, placement)
            outcome.updated += 1
        if not row.enriched_title:
            merchant = merchant_of(row.description, row.counterparty)
            enrich_row(row, merchant.title, None)
    session.commit()
    return outcome


def _rules_sentence(applied: int, failed: int, skipped: int) -> str:
    """The one line to write about a card that has just been applied, counted here.

    Handed to the model as `say`, because a model given a finished line writes it back word for
    word: the resumed half of a card turn listed every merchant it had applied as a bullet list
    above the next card, which the card below already said (left by ticket 30). The counts are
    the same ones the `applied` line is built from, so the two can never disagree.
    """
    parts = [f"{applied} merchant now has a rule" if applied == 1 else f"{applied} merchants now have rules"]
    if failed:
        parts.append("1 could not be stored" if failed == 1 else f"{failed} could not be stored")
    if skipped:
        parts.append("1 is still to decide" if skipped == 1 else f"{skipped} are still to decide")
    if len(parts) == 1:
        return f"{parts[0]}."
    return f"{', '.join(parts[:-1])} and {parts[-1]}."


def apply_answers(
    session: Session, profile_id: str, rows: Sequence[AskRow], answers: Sequence[AskAnswer]
) -> Applied | None:
    """Turn every answered row of a Question card into a category rule, here in code.

    This is the whole point of the card: the user's decision is applied by `set_rule` before
    the model runs again, so the rows move even if the model then says nothing useful. Asking
    the fast model to make one tool call per answer is what looped for minutes and stored
    nothing (review of 2026-09-04).

    `line` goes onto the card the moment the answers are applied and `say` is the one sentence
    the model is asked to write instead of repeating it. `None` means nothing was decided
    (every row skipped).
    """
    labels = {row.ref: row.label for row in rows}
    answered: set[str] = set()
    applied: list[str] = []
    failed: list[str] = []
    for answer in answers:
        choice = (answer.value or answer.text or "").strip()
        if not choice:
            continue
        answered.add(answer.ref)
        label = labels.get(answer.ref, answer.ref)
        head, tail = split_choice(choice)
        outcome = set_rule(session, profile_id, pattern=answer.ref, category=head, subcategory=tail)
        if outcome.error is not None:
            failed.append(f"{label}: {outcome.error}")
            continue
        assert outcome.placement is not None
        applied.append(f"{label} -> {outcome.placement.label} ({outcome.updated} bookings recategorized)")
    if not applied and not failed:
        return None
    skipped = [label for ref, label in labels.items() if ref not in answered]
    said: list[str] = []
    if applied:
        said.append("Applied: " + ", ".join(applied))
    if failed:
        said.append("Could not apply: " + "; ".join(failed))
    if skipped:
        said.append("Left for later: " + ", ".join(skipped))
    return Applied(line=". ".join(said) + ".", say=_rules_sentence(len(applied), len(failed), len(skipped)))
