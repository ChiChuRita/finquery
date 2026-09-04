"""Reading bookings out of a PDF or a photo, and proving them before they are written.

`pdf` gets the text and the page images out of a file, `layouts` says which bank printed it and
what to tell the model about it, `subagent` is the extraction sub-agent (spans in, spans out),
`guards` holds those spans to the page and to the statement's arithmetic (ADR 0011), `statement`
is the pipeline the two entry points call, `review` is the card for what the guards flagged and
`bill` is the receipt flow. Everything ends at `ingest.commit.commit_rows`, the same commit a
CSV import uses.
"""
