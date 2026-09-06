"""The five generated households: deterministic, and true to their truth file.

The truth file is what a judge recomputes a figure from, so the one thing worth testing is that
it agrees with the database the production import path builds out of the same CSV, merchant by
merchant and month by month. If a dictionary entry moves, this is what says so.
"""

import json

import pytest
from sqlalchemy import text

from finquery.db import QUERY_VIEW
from training.data.households import SHIPPED, load_households, open_household

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import generate_synthetic  # noqa: E402

GENERATED = [slug for slug in load_households() if slug != SHIPPED]


def test_six_households_with_the_shipped_year_first():
    households = load_households()
    assert list(households) == [SHIPPED, "student", "family", "freelancer", "pensioner", "couple"]
    assert len(households["couple"].accounts) == 2
    for entry in households.values():
        assert entry.today.isoformat() == "2025-12-31"


def test_generation_is_deterministic():
    """Two runs of the generator produce the same bookings, so the fixtures never churn."""
    for household in generate_synthetic.HOUSEHOLDS:
        first = generate_synthetic.generate_household(household)
        second = generate_synthetic.generate_household(household)
        assert first == second


def test_committed_csv_matches_the_generator():
    """The committed files are what the generator writes today, not what it wrote once."""
    for household in generate_synthetic.HOUSEHOLDS:
        ledgers = generate_synthetic.generate_household(household)
        for ledger, rows in zip(household.ledgers, ledgers, strict=True):
            path = generate_synthetic.HOUSEHOLDS_OUT / ledger.file_name
            written = path.read_bytes()
            assert written.count(b"\r\n") == len(rows) + 1, f"{ledger.file_name} has moved"
            assert len(written) < 100_000, f"{ledger.file_name} is over 100 KB"


def test_every_household_carries_a_needs_review_bucket_and_both_signs():
    truth = json.loads(generate_synthetic.HOUSEHOLDS_OUT.joinpath("households.json").read_text("utf-8"))
    for entry in truth["households"]:
        assert entry["needs_review_bookings"] > 0, entry["slug"]
        assert entry["spent_eur"] > 0 and entry["received_eur"] > 0, entry["slug"]
        assert len(entry["monthly"]) == 12, entry["slug"]
        assert entry["edge_cases"], entry["slug"]


def _merchants(slug: str) -> dict[str, tuple[str, str | None, int, float]]:
    session_factory, profile_id, _entry = open_household(slug)
    try:
        with session_factory() as session:
            rows = (
                session.execute(
                    text(
                        f"""
                        SELECT coalesce(counterparty, description)            AS merchant,
                               coalesce(category, 'Needs review')             AS topic,
                               subcategory                                    AS sub,
                               count(*)                                       AS bookings,
                               round(-sum(CASE WHEN amount < 0 THEN amount ELSE 0 END), 2) AS spent
                        FROM {QUERY_VIEW}
                        WHERE profile_id = :profile_id
                        GROUP BY merchant, topic, sub
                        """
                    ),
                    {"profile_id": profile_id},
                )
                .mappings()
                .all()
            )
    finally:
        session_factory.kw["bind"].dispose()
    return {row["merchant"]: (row["topic"], row["sub"], row["bookings"], row["spent"]) for row in rows}


@pytest.mark.parametrize("slug", GENERATED)
def test_the_database_agrees_with_the_truth_file(slug: str):
    entry = load_households()[slug]
    have = _merchants(slug)
    assert set(have) == {merchant["name"] for merchant in entry.truth["merchants"]}
    for merchant in entry.truth["merchants"]:
        topic, sub, bookings, spent = have[merchant["name"]]
        assert (topic, sub) == (merchant["category"], merchant["subcategory"]), merchant["name"]
        assert bookings == merchant["bookings"], merchant["name"]
        assert spent == pytest.approx(merchant["spent_eur"], abs=0.005), merchant["name"]


@pytest.mark.parametrize("slug", GENERATED)
def test_the_monthly_totals_agree_with_the_truth_file(slug: str):
    entry = load_households()[slug]
    session_factory, profile_id, _ = open_household(slug)
    try:
        with session_factory() as session:
            rows = (
                session.execute(
                    text(
                        f"""
                        SELECT strftime('%Y-%m', booked_on) AS month,
                               round(-sum(CASE WHEN amount < 0 THEN amount ELSE 0 END), 2) AS spent,
                               round(sum(CASE WHEN amount > 0 THEN amount ELSE 0 END), 2)  AS received
                        FROM {QUERY_VIEW}
                        WHERE profile_id = :profile_id
                        GROUP BY month
                        """
                    ),
                    {"profile_id": profile_id},
                )
                .mappings()
                .all()
            )
    finally:
        session_factory.kw["bind"].dispose()
    have = {row["month"]: (row["spent"], row["received"]) for row in rows}
    for month in entry.truth["monthly"]:
        spent, received = have[month["month"]]
        assert spent == pytest.approx(month["spent_eur"], abs=0.005), month["month"]
        assert received == pytest.approx(month["received_eur"], abs=0.005), month["month"]
