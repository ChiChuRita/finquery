"""The six households and the databases the gate runs against.

One database per household, built by the production import path: the same preset, the same
reader, the same `commit_rows` and the same categorizer with the model stage switched off that
`bench.finquery_bench.dataset` uses for the benchmark. No model runs while a database is built,
so a figure computed against one is the same figure tomorrow.

Building six of them costs about a minute, so they are cached under `training/data/.db/`, keyed
by a hash of the CSV files that went into them. Change a fixture and the next run rebuilds.

    uv run python -m training.data.households list
    uv run python -m training.data.households build
    uv run python -m training.data.households build --slug student --rebuild
"""

import argparse
import asyncio
import hashlib
import json
import shutil
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from finquery.categorize import categorize_import
from finquery.db import Profile, create_profile, make_session_factory
from finquery.ingest.commit import commit_rows
from finquery.ingest.csv_reader import detect_preset, mapping_for, parse, sniff
from finquery.providers import ModelRole, ProviderNotAvailable
from finquery.query.subagent import QueryContext, load_query_context

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "fixtures" / "synthetic"
TRUTH_FILE = FIXTURES / "households" / "households.json"
CACHE = Path(__file__).resolve().parent / ".db"

SHIPPED = "shipped"
"""The slug of the year the app ships with. It is the sixth household, and the one the
benchmark is written against, so a training question about it must be a new question."""

SHIPPED_LABEL = "Berlin household, the shipped year"
SHIPPED_FILE = FIXTURES / "sparkasse-2025.csv"
SHIPPED_ACCOUNT = "Sparkasse Girokonto"
SHIPPED_TODAY = date(2025, 12, 31)
"""What a question about the shipped year is asked on, the same pin `bench/` uses."""

VERSION = 1
"""Bumped when the build changes, so cached databases from before it are not reused."""


class HouseholdUnknown(KeyError):
    """A slug no household carries. The message lists the six that exist."""


def no_model(_role: ModelRole):  # noqa: ANN201 - it never returns, it raises
    """The resolver the loader hands the categorizer: there is no model in a training database.

    `categorize_rows` treats an unavailable provider as "the model stage placed nothing", so the
    rules and the merchant dictionary place what they know and the rest stays Needs review.
    """
    raise ProviderNotAvailable("a training database is built without a model")


@dataclass(frozen=True)
class Account:
    """One account of a household: one CSV file, imported under one name."""

    name: str
    path: Path


@dataclass(frozen=True)
class Household:
    """One household: its files, the day its questions are asked on, and its truth."""

    slug: str
    label: str
    today: date
    accounts: tuple[Account, ...]
    truth: dict[str, Any] = field(default_factory=dict)

    @property
    def note(self) -> str:
        return str(self.truth.get("note", ""))

    def fingerprint(self) -> str:
        """A hash of everything that goes into the database, so a stale cache is never used."""
        digest = hashlib.sha256(f"v{VERSION}:{self.slug}".encode())
        for account in self.accounts:
            digest.update(account.name.encode())
            digest.update(account.path.read_bytes())
        return digest.hexdigest()[:16]

    @property
    def database(self) -> Path:
        return CACHE / f"{self.slug}-{self.fingerprint()}.sqlite"


def _shipped() -> Household:
    return Household(
        slug=SHIPPED,
        label=SHIPPED_LABEL,
        today=SHIPPED_TODAY,
        accounts=(Account(name=SHIPPED_ACCOUNT, path=SHIPPED_FILE),),
        truth={
            "slug": SHIPPED,
            "label": SHIPPED_LABEL,
            "note": (
                "The year the app ships with, and the year the benchmark is written against: a "
                "training question about it has to be a new question, never a benchmark one."
            ),
        },
    )


def load_households() -> dict[str, Household]:
    """The six households, the shipped year first, keyed by slug."""
    households = {SHIPPED: _shipped()}
    payload = json.loads(TRUTH_FILE.read_text(encoding="utf-8"))
    for truth in payload["households"]:
        households[truth["slug"]] = Household(
            slug=truth["slug"],
            label=truth["label"],
            today=date.fromisoformat(truth["today"]),
            accounts=tuple(
                Account(name=account["name"], path=FIXTURES / Path(account["file"]))
                for account in truth["accounts"]
            ),
            truth=truth,
        )
    return households


def household(slug: str) -> Household:
    households = load_households()
    if slug not in households:
        raise HouseholdUnknown(f"no household {slug!r}; the six are {', '.join(households)}")
    return households[slug]


def _import(session_factory: sessionmaker[Session], profile_id: str, account: Account) -> None:
    """One CSV through the production path: sniff, preset, parse, commit, categorize."""
    sniffed = sniff(account.path.read_bytes())
    preset = detect_preset(sniffed.header)
    if preset is None:
        raise RuntimeError(f"{account.path.name} is no longer recognized by any preset")
    mapping = mapping_for(preset, sniffed.header)
    parsed = parse(sniffed, mapping)
    with session_factory() as session:
        record = commit_rows(
            session,
            profile_id,
            rows=parsed.rows,
            mapping=mapping,
            account_name=account.name,
            file_name=account.path.name,
            preset=preset.name,
        )
        import_id = record.id
    with session_factory() as session:
        asyncio.run(categorize_import(session, profile_id, import_id, resolve_model=no_model))


def build(entry: Household, *, rebuild: bool = False) -> Path:
    """Build this household's database if the cache does not already hold it."""
    target = entry.database
    if target.exists() and not rebuild:
        return target
    target.unlink(missing_ok=True)
    working = target.with_suffix(".building")
    working.unlink(missing_ok=True)
    session_factory = make_session_factory(working)
    with session_factory() as session:
        profile = create_profile(session, entry.label)
        profile_id = profile.id
    for account in entry.accounts:
        _import(session_factory, profile_id, account)
    session_factory.kw["bind"].dispose()
    # Written under another name and moved, so an interrupted build never leaves a database
    # that looks finished behind.
    working.replace(target)
    return target


def open_household(slug: str, *, rebuild: bool = False) -> tuple[sessionmaker[Session], str, Household]:
    """The session factory, the profile id and the household. Builds the database if needed."""
    entry = household(slug)
    path = build(entry, rebuild=rebuild)
    session_factory = make_session_factory(path)
    with session_factory() as session:
        profile_id = session.scalars(select(Profile)).one().id
    return session_factory, profile_id, entry


def context_of(slug: str, *, rebuild: bool = False) -> tuple[sessionmaker[Session], str, QueryContext, Household]:
    """What every prompt builder needs: the database, the profile and its `QueryContext`.

    `today` comes from the household and not from the clock, exactly as the benchmark pins it:
    without that, "last month" would ask about a month a year after the newest booking.
    """
    session_factory, profile_id, entry = open_household(slug, rebuild=rebuild)
    with session_factory() as session:
        context = load_query_context(session, profile_id, today=entry.today)
    return session_factory, profile_id, context, entry


def _counts(slug: str, *, rebuild: bool) -> dict[str, Any]:
    session_factory, _profile_id, context, entry = context_of(slug, rebuild=rebuild)
    session_factory.kw["bind"].dispose()
    return {
        "slug": slug,
        "label": entry.label,
        "accounts": len(entry.accounts),
        "bookings": context.transaction_count,
        "categorized": context.categorized_count,
        "needs_review": context.transaction_count - context.categorized_count,
        "first": context.first_booked_on,
        "last": context.last_booked_on,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="The households and their cached databases.")
    parser.add_argument("command", choices=("list", "build", "clean"))
    parser.add_argument("--slug", action="append", help="one household; repeatable, all by default")
    parser.add_argument("--rebuild", action="store_true", help="build again even when cached")
    args = parser.parse_args(argv)

    households = load_households()
    slugs = args.slug or list(households)
    for slug in slugs:
        if slug not in households:
            print(f"no household {slug!r}; the six are {', '.join(households)}", file=sys.stderr)
            return 2

    if args.command == "clean":
        shutil.rmtree(CACHE, ignore_errors=True)
        print(f"removed {CACHE}")
        return 0
    if args.command == "list":
        for slug in slugs:
            entry = households[slug]
            print(f"{slug:11} {len(entry.accounts)} account(s)  {entry.label}")
            print(f"            {entry.note}")
        return 0
    for slug in slugs:
        counts = _counts(slug, rebuild=args.rebuild)
        print(
            f"{counts['slug']:11} {counts['bookings']:4} bookings  "
            f"{counts['categorized']:4} categorized  {counts['needs_review']:4} needs review  "
            f"{counts['first']} to {counts['last']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
