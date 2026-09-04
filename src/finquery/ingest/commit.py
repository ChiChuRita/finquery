"""Committing parsed rows into the profile, with one import record to show for it."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from finquery.db import Import, Transaction, ensure_account, fingerprint
from finquery.ingest.csv_reader import Mapping, ParsedRow
from finquery.ingest.duplicates import Matcher, hold


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
    """Insert the rows the profile does not have and hold the rest aside for a decision.

    Every ingestion path lands here (the Import page, `import_file` in a chat, and the
    extraction path of ticket 11), which is why duplicate detection lives at this seam: a row
    that matches a booking the profile already has, exactly or nearly, becomes a
    `duplicate_candidate` instead of a transaction. Nothing is inserted and nothing is dropped
    without the user answering Keep both or Remove. See `finquery.ingest.duplicates`.
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

    matcher = Matcher(session, profile_id, account.id)
    duplicates = 0
    for row in rows:
        match = matcher.take(row.booked_on, row.amount_cents, row.description)
        if match is not None:
            duplicates += 1
            hold(
                session,
                profile_id,
                account_id=account.id,
                booked_on=row.booked_on,
                amount_cents=row.amount_cents,
                description=row.description,
                counterparty=row.counterparty,
                match=match,
                import_id=record.id,
            )
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
                fingerprint=fingerprint(account.id, row.booked_on, row.amount_cents, row.description),
            )
        )

    record.imported_count = len(rows) - duplicates
    record.duplicate_count = duplicates
    session.commit()
    return record


def import_summary(session: Session, record: Import, account_name: str) -> str:
    """What one import came to, in one sentence counted here rather than written by a model.

    Both places that report an import use it: the seeded first turn of a review conversation
    and the `import_file` tool, so the same import reads the same either way. Call it after
    categorization, so the categorized count is the final one.
    """
    rows, categorized = session.execute(
        select(func.count(Transaction.id), func.count(Transaction.category_id)).where(
            Transaction.import_id == record.id
        )
    ).one()
    lines = [
        f"I imported **{record.imported_count} of {record.row_count} bookings** from "
        f"`{record.file_name}` into {account_name}."
    ]
    decided = record.duplicates_kept + record.duplicates_removed
    if decided:
        lines.append(
            f"Of {record.duplicate_count} bookings that looked like duplicates, "
            f"{record.duplicates_kept} were kept and {record.duplicates_removed} removed."
        )
    if record.duplicate_count - decided:
        waiting = record.duplicate_count - decided
        lines.append(
            f"{waiting} look like bookings you already have and are waiting for your decision, "
            "so nothing was added for them yet."
        )
    lines.append(f"{categorized} of {rows} are categorized, {rows - categorized} are still Needs review.")
    return " ".join(lines)
