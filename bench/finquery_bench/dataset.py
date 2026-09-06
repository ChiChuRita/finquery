"""The database every benchmark run and every gold row is computed against.

One fresh in-memory database holding the shipped synthetic year, imported through the same
Sparkasse preset the app uses and categorized by the same pipeline, with the model stage
switched off: the profile's rules and the merchant dictionary place what they know and the rest
stays Needs review. No model means the database is the same every time, which is what makes a
gold row reproducible and `Needs review` an honest bucket to ask questions about.
"""

import asyncio
from contextlib import contextmanager
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from finquery.categorize import categorize_import
from finquery.db import create_profile, make_session_factory
from finquery.ingest.commit import commit_rows
from finquery.ingest.csv_reader import detect_preset, mapping_for, parse, sniff
from finquery.providers import ModelRole, ProviderNotAvailable

REPO = Path(__file__).resolve().parents[2]
SYNTHETIC_CSV = REPO / "fixtures" / "synthetic" / "sparkasse-2025.csv"

PROFILE_NAME = "Benchmark"


def no_model(_role: ModelRole):  # noqa: ANN201 - it never returns, it raises
    """The resolver the loader hands the categorizer: there is no model in a gold database.

    `categorize_rows` treats an unavailable provider as "the model stage placed nothing", so
    stages one and two still run and everything they do not know stays Needs review.
    """
    raise ProviderNotAvailable("the benchmark database is built without a model")


def load_synthetic_year(session_factory: sessionmaker[Session]) -> str:
    """Import and categorize the synthetic year into a new profile. Returns its id."""
    with session_factory() as session:
        profile = create_profile(session, PROFILE_NAME)
        profile_id = profile.id

    sniffed = sniff(SYNTHETIC_CSV.read_bytes())
    preset = detect_preset(sniffed.header)
    if preset is None:
        raise RuntimeError(f"{SYNTHETIC_CSV.name} is no longer recognized by any preset")
    parsed = parse(sniffed, mapping_for(preset, sniffed.header))

    with session_factory() as session:
        record = commit_rows(
            session,
            profile_id,
            rows=parsed.rows,
            mapping=mapping_for(preset, sniffed.header),
            account_name=preset.account_name,
            file_name=SYNTHETIC_CSV.name,
            preset=preset.name,
        )
        import_id = record.id

    with session_factory() as session:
        asyncio.run(categorize_import(session, profile_id, import_id, resolve_model=no_model))
    return profile_id


@contextmanager
def fresh_database() -> Iterator[tuple[sessionmaker[Session], str]]:
    """A database holding nothing but the synthetic year, for the duration of the block."""
    session_factory = make_session_factory(":memory:")
    try:
        yield session_factory, load_synthetic_year(session_factory)
    finally:
        # An in-memory database is one connection held open by a StaticPool, so a process that
        # builds several (the tests, a compare run) has to let each one go.
        session_factory.kw["bind"].dispose()
