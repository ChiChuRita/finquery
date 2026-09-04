"""The mapping sub-agent: it proposes a column mapping for a bank we do not have a preset for.

Fast slot, one forced tool call, no free-form text. The user always sees the proposal before
anything is committed and can correct every field, on the Question card `import_file` asks the
file's own columns with. So a wrong guess costs a click. Files from a recognized bank never
reach this module.

`propose` is the whole call: it runs the sub-agent and snaps the column names it answered with
onto the real header, so a caller only ever sees a mapping the file can be parsed with.
"""

from pydantic_ai import Agent, ToolOutput
from pydantic_ai.models import Model
from pydantic_ai.settings import ModelSettings

from finquery.ingest.csv_reader import ProposedMapping, Sniffed, normalize

INSTRUCTIONS = """\
You map the columns of a bank CSV export onto a fixed set of fields. You are given the header
and the first rows of one file. Call `propose_mapping` exactly once with your answer.

Rules:
- Copy column names exactly as they appear in the header, including case and punctuation.
- Use `amount_column` when one column holds a signed amount. Use `debit_column` and
  `credit_column` when outgoing and incoming money live in two columns; values there are
  written without a sign.
- `description_column` is the booking text, `counterparty_column` the other party's name.
  Leave a field out when the file has no such column.
- `date_format` describes the booking date column: 01.02.2025 is DD.MM.YYYY, 01.02.25 is
  DD.MM.YY, 2025-02-01 is YYYY-MM-DD.
- `decimal_separator` is "comma" for 1.234,56 and "dot" for 1,234.56.
- `account_name` is a short human name for the account, taken from the bank or the file.
"""

SAMPLE_ROWS = 5


class MappingUnusable(ValueError):
    """The model answered, but not with a mapping this file can be read by."""


mapping_agent = Agent(
    instructions=INSTRUCTIONS,
    output_type=ToolOutput(ProposedMapping, name="propose_mapping"),
    name="finquery-csv-mapping",
)


async def propose(
    sniffed: Sniffed,
    file_name: str,
    *,
    model: Model,
    model_settings: ModelSettings | None = None,
) -> ProposedMapping:
    """One mapping proposal for a header no preset recognized.

    Raises `MappingUnusable` when the model names a column the file does not have, which is the
    one failure a caller cannot repair. A name that only differs in case or punctuation from the
    real header is repaired here instead of refused.
    """
    result = await mapping_agent.run(
        mapping_prompt(sniffed, file_name), model=model, model_settings=model_settings
    )
    proposal = result.output
    known = {normalize(name): name for name in sniffed.header}
    columns = {
        name: value
        for name, value in proposal.mapping.model_dump().items()
        if name.endswith("_column") and value is not None
    }
    unknown = [value for value in columns.values() if normalize(value) not in known]
    if unknown:
        raise MappingUnusable(f"The model proposed columns the file does not have: {', '.join(unknown)}.")
    mapping = proposal.mapping.model_copy(update={name: known[normalize(value)] for name, value in columns.items()})
    return proposal.model_copy(update={"mapping": mapping})


def mapping_prompt(sniffed: Sniffed, file_name: str) -> str:
    lines = [f"File: {file_name}", f"Delimiter: {sniffed.delimiter!r}", "", "Header:"]
    lines += [f"- {name}" for name in sniffed.header]
    lines += ["", f"First {SAMPLE_ROWS} rows, one column per line:"]
    for number, row in enumerate(sniffed.rows[:SAMPLE_ROWS], start=1):
        lines.append(f"Row {number}:")
        lines += [f"  {name} = {value}" for name, value in zip(sniffed.header, row, strict=False) if value.strip()]
    return "\n".join(lines)
