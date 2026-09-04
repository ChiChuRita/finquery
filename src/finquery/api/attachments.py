"""The wire side of chat attachments: taking them out of a message, and serving them back.

`useChat` sends an attachment as a file part whose URL is a data URL. Two things happen to it
here before the agent ever sees the message:

1. the part is taken out of the client's message, so the bytes never enter the prompt (a bank
   CSV would be tens of thousands of tokens, and the model has no use for them: `import_file`
   reads the stored file instead),
2. the bytes are stored per conversation (`finquery.attachments`) and the turn being written
   gets a file part pointing at this module's endpoint, so a reloaded transcript shows the same
   chip the live one did.
"""

from collections.abc import Sequence

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic_ai.messages import BinaryContent
from pydantic_ai.ui.vercel_ai.request_types import FileUIPart, TextUIPart, UIMessage
from sqlalchemy.orm import Session

from finquery.attachments import MAX_FILES_PER_MESSAGE, AttachmentRejected, Upload, of_turn, store
from finquery.db import Attachment

router = APIRouter()

DEFAULT_MEDIA_TYPE = "application/octet-stream"


def take_uploads(messages: Sequence[UIMessage]) -> list[Upload]:
    """Remove the file parts from these messages and return what they carried.

    A file part whose URL is not a data URL is dropped: the composer only ever sends data URLs,
    and a URL the server would have to fetch is not something a client gets to ask for.
    """
    uploads: list[Upload] = []
    for message in messages:
        if message.role != "user":
            continue
        kept = []
        taken: list[str] = []
        for part in message.parts:
            if not isinstance(part, FileUIPart):
                kept.append(part)
                continue
            try:
                content = BinaryContent.from_data_uri(part.url)
            except ValueError:
                continue
            taken.append(part.filename or "attachment")
            uploads.append(
                Upload(
                    file_name=part.filename or "attachment",
                    media_type=part.media_type or content.media_type or DEFAULT_MEDIA_TYPE,
                    data=content.data,
                )
            )
        # A file dropped in and sent with no text would leave the turn without a prompt at all,
        # so it gets the one sentence the user's gesture meant. What can be done with the file
        # is in the agent's instructions, not here.
        if taken and not any(isinstance(part, TextUIPart) and part.text.strip() for part in kept):
            kept = [TextUIPart(text=f"I attached {', '.join(taken)}.")]
        message.parts = kept
    if len(uploads) > MAX_FILES_PER_MESSAGE:
        raise AttachmentRejected(f"One message may carry at most {MAX_FILES_PER_MESSAGE} files.")
    return uploads


def store_uploads(
    session: Session,
    profile_id: str,
    conversation_id: str,
    turn_position: int,
    uploads: Sequence[Upload],
) -> list[Attachment]:
    stored = [store(session, profile_id, conversation_id, turn_position, upload) for upload in uploads]
    session.commit()
    return stored


def chips(records: Sequence[Attachment]) -> list[FileUIPart]:
    """The attachment chips of one turn, as the transcript renders them after a reload."""
    return [
        FileUIPart(url=f"/api/attachments/{record.id}", media_type=record.media_type, filename=record.file_name)
        for record in records
    ]


def turn_chips(session: Session, conversation_id: str, turn_position: int) -> list[FileUIPart]:
    return chips(of_turn(session, conversation_id, turn_position))


@router.get("/attachments/{attachment_id}")
async def download_attachment(request: Request, attachment_id: str) -> Response:
    """The stored file itself, which is what the chip in the transcript links to."""
    with request.app.state.session_factory() as session:
        record = session.get(Attachment, attachment_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Attachment not found")
        return Response(
            content=record.data,
            media_type=record.media_type or DEFAULT_MEDIA_TYPE,
            headers={"content-disposition": f'inline; filename="{record.file_name}"'},
        )
