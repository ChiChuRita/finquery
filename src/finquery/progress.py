"""Progress a chat tool streams into its own tool step while it works.

An import reads a file, commits hundreds of rows and then asks the categorizer: seconds in
which the transcript would otherwise show nothing but a spinner. Pydantic AI carries the
updates as custom events (`RunContext.emit` from an async tool), and the Vercel adapter turns
each one into a data part attributed to the tool call it came from.

The parts are transient: they are streamed and shown live, and never stored. What a reloaded
transcript needs is the tool's result (the import summary), not the counting that led to it.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

from pydantic_ai import CustomEvent, RunContext
from pydantic_ai.ui.vercel_ai.response_types import DataChunk

logger = logging.getLogger(__name__)

PROGRESS_PART = "data-import_progress"
"""The data part the transcript renders inside the running tool step."""


@dataclass(kw_only=True)
class ImportProgress(CustomEvent, name="import_progress"):
    """One line of progress: what stage the tool is in, and the counts it has so far."""

    stage: str
    message: str
    counts: dict[str, int] = field(default_factory=dict)

    def to_payload(self) -> DataChunk:
        # A chunk rather than a bare payload, because that is the only way to mark the part
        # transient. The tool call id rides along so the frontend can put the line in the step
        # it belongs to.
        return DataChunk(
            type=PROGRESS_PART,
            data={
                "stage": self.stage,
                "message": self.message,
                "counts": self.counts,
                "tool_call_id": self.tool_call_id,
            },
            transient=True,
        )


async def report(ctx: RunContext[Any], stage: str, message: str, **counts: int) -> None:
    """Stream one progress line. Never lets a tool fail because nobody was listening."""
    try:
        await ctx.emit(ImportProgress(stage=stage, message=message, counts=counts))
    except Exception:
        # A run with no event stream (or a consumer that went away) still has work to finish.
        logger.debug("progress %s could not be emitted", stage, exc_info=True)
