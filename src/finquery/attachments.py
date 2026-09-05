"""Files dropped into the chat composer, stored per conversation.

The composer sends an attachment as a data URL inside the user message. The bytes are taken out
of that message before the run starts (`finquery.api.attachments`) and stored here, so:

- the prompt stays small: the model is told a file is attached and reads it through
  `import_file`, instead of carrying a 20 MB CSV into its context,
- a reload still shows the attachment chip, because the stored row knows which turn the file
  was sent with,
- and the ingestion pipeline gets bytes it can read twice, which is what a mapping the user has
  to confirm needs (propose, ask, commit).

Identity is the content hash per conversation: the same file dropped twice is one row. The
handle the model uses is the file name, because that is what it can copy without a mistake;
`find` also accepts the row id and a unique partial name.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from hashlib import sha256
from pathlib import PurePosixPath
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from finquery.db import Attachment

MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024
"""Per file, the same ceiling the REST upload endpoint puts on a file."""

MAX_FILES_PER_MESSAGE = 5

BRIEF_FILES = 8
"""Attachments named in the prompt: the newest few, so a long conversation stays small."""

AttachmentKind = Literal["csv", "pdf", "image", "other"]

CSV_SUFFIXES = (".csv", ".tsv", ".txt")
CSV_MEDIA_TYPES = ("text/csv", "text/tab-separated-values", "application/csv", "text/plain")

class AttachmentRejected(ValueError):
    """The upload is not something a conversation may carry."""


@dataclass(frozen=True)
class Upload:
    """One file as it arrived, before it is stored."""

    file_name: str
    media_type: str
    data: bytes


def kind_of(file_name: str, media_type: str) -> AttachmentKind:
    """Which reader of the ingestion pipeline can take this file.

    The suffix decides before the media type does: browsers report a CSV as `text/csv`,
    `application/vnd.ms-excel` or `text/plain` depending on the platform.
    """
    suffix = PurePosixPath(file_name).suffix.lower()
    if suffix in CSV_SUFFIXES or media_type.lower() in CSV_MEDIA_TYPES:
        return "csv"
    if suffix == ".pdf" or media_type.lower() == "application/pdf":
        return "pdf"
    if media_type.lower().startswith("image/") or suffix in (".png", ".jpg", ".jpeg", ".webp", ".heic"):
        return "image"
    return "other"


def store(
    session: Session,
    profile_id: str,
    conversation_id: str,
    turn_position: int,
    upload: Upload,
) -> Attachment:
    """Store one upload, or return the row this conversation already has for those bytes.

    Raises `AttachmentRejected` for an empty file, one over the size limit, or a kind no reader
    of ours could ever take.
    """
    if not upload.data:
        raise AttachmentRejected(f"{upload.file_name} is empty, so there is nothing to read in it.")
    if len(upload.data) > MAX_ATTACHMENT_BYTES:
        raise AttachmentRejected(
            f"{upload.file_name} is larger than {MAX_ATTACHMENT_BYTES // (1024 * 1024)} MB. "
            "Export a shorter date range from your bank and attach that."
        )
    kind = kind_of(upload.file_name, upload.media_type)
    if kind == "other":
        raise AttachmentRejected(
            f"{upload.file_name} is not a kind FinQuery can read. Attach a CSV, a PDF or an image."
        )

    digest = sha256(upload.data).hexdigest()
    existing = session.scalars(
        select(Attachment).where(Attachment.conversation_id == conversation_id, Attachment.sha256 == digest)
    ).one_or_none()
    if existing is not None:
        # Re-attaching a file the conversation already has moves its chip to this turn rather
        # than storing the bytes again.
        existing.turn_position = turn_position
        return existing

    record = Attachment(
        profile_id=profile_id,
        conversation_id=conversation_id,
        turn_position=turn_position,
        file_name=upload.file_name,
        media_type=upload.media_type,
        kind=kind,
        size_bytes=len(upload.data),
        sha256=digest,
        data=upload.data,
    )
    session.add(record)
    return record


def of_conversation(session: Session, conversation_id: str) -> list[Attachment]:
    """Everything attached to this conversation, newest first."""
    return list(
        session.scalars(
            select(Attachment)
            .where(Attachment.conversation_id == conversation_id)
            .order_by(Attachment.created_at.desc())
        ).all()
    )


def of_turn(session: Session, conversation_id: str, turn_position: int) -> list[Attachment]:
    """The files sent with one turn, which is where the transcript shows their chips."""
    return list(
        session.scalars(
            select(Attachment)
            .where(
                Attachment.conversation_id == conversation_id,
                Attachment.turn_position == turn_position,
            )
            .order_by(Attachment.created_at)
        ).all()
    )


def find(session: Session, conversation_id: str, ref: str) -> Attachment | None:
    """The attachment the assistant means: its file name, its id, or a unique part of the name."""
    wanted = ref.strip().strip("`\"'").casefold()
    if not wanted:
        return None
    candidates = of_conversation(session, conversation_id)
    for record in candidates:
        if record.id == ref or record.file_name.casefold() == wanted:
            return record
    partial = [record for record in candidates if wanted in record.file_name.casefold()]
    return partial[0] if len(partial) == 1 else None


def human_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.0f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


def _state_of(record: Attachment) -> str:
    if record.import_id is not None:
        return "already imported"
    if record.mapping_json is not None:
        return "waiting for the column mapping to be confirmed"
    return "not imported yet"


def brief(records: Sequence[Attachment]) -> str:
    """What the assistant is told about the files of this conversation.

    The file name is the handle: `import_file` takes it, and it is the one thing about an
    attachment a model can copy without getting it wrong.
    """
    if not records:
        return ""
    lines = [
        "Files attached in this conversation, newest first. Call `import_file` with the file "
        "name to turn one into transactions:"
    ]
    for record in records[:BRIEF_FILES]:
        lines.append(
            f"- `{record.file_name}` ({record.kind.upper()}, {human_size(record.size_bytes)}, "
            f"{_state_of(record)})"
        )
    return "\n".join(lines)
