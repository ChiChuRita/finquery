"""Committing parsed rows into the profile, with one import record to show for it."""

from collections import Counter

from sqlalchemy.orm import Session

from finquery.db import Import, Transaction, ensure_account, fingerprint
from finquery.ingest.csv_reader import Mapping, ParsedRow


def commit_rows(
    session: Session,
    profile_id: str,
    *,
    rows: list[ParsedRow],
    mapping: Mapping,
    account_name: str,
    file_name: str,
    kind: str = "csv",
    preset: str | None = None,
    skipped_count: int = 0,
) -> Import:
    """Insert rows the profile does not have yet and record the import.

    A row whose fingerprint already exists in the profile is counted as a duplicate and not
    inserted, matching each incoming row against at most one existing booking so a genuinely
    repeated payment still lands. Ticket 10 turns that count into a question per candidate
    instead of a silent skip.
    """
    account = ensure_account(session, profile_id, account_name)
    record = Import(
        profile_id=profile_id,
        account_id=account.id,
        file_name=file_name,
        kind=kind,
        preset=preset,
        mapping_json=mapping.model_dump_json(),
        row_count=len(rows) + skipped_count,
        skipped_count=skipped_count,
    )
    session.add(record)
    session.flush()

    seen = Counter(
        value for (value,) in session.query(Transaction.fingerprint).filter_by(profile_id=profile_id).all()
    )
    duplicates = 0
    for row in rows:
        value = fingerprint(account.id, row.booked_on, row.amount_cents, row.description)
        if seen[value]:
            seen[value] -= 1
            duplicates += 1
            continue
        session.add(
            Transaction(
                profile_id=profile_id,
                account_id=account.id,
                booked_on=row.booked_on,
                amount_cents=row.amount_cents,
                description=row.description,
                counterparty=row.counterparty,
                source="import",
                import_id=record.id,
                fingerprint=value,
            )
        )

    record.imported_count = len(rows) - duplicates
    record.duplicate_count = duplicates
    session.commit()
    return record
