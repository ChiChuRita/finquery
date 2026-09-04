# 08: Import through chat attachments and text

**What to build:** A user drops a CSV, PDF or image into the chat composer and sends it. The assistant runs the import as a tool with progress streamed into the tool step, then continues in the same conversation with the categorization questions. A pasted statement snippet or a typed sentence like "I paid 12 EUR cash for lunch today" produces a preview card of the extracted transaction with Confirm and Discard.

**Blocked by:** 07 Categorization at import with Question card

**Status:** ready-for-agent

- [ ] Composer accepts CSV, PDF and image attachments; file parts reach the server and are stored per conversation
- [ ] `import_file` tool runs the ingestion pipeline for CSV now and delegates PDF and images to the extraction path (which lands in ticket 11); progress as transient data parts
- [ ] Mapping confirmation for unknown CSV layouts happens through the Question card
- [ ] Pasted or typed transactions are extracted by the fast slot and shown as a preview card; Confirm creates the transaction and categorizes it
- [ ] HTTP-seam tests: CSV attachment import end to end, typed transaction preview and confirm
- [ ] Browser verification of drop, progress, questions, and a typed transaction
