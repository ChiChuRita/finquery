# 07: Categorization at import with Question card

**What to build:** After an import, transactions are categorized in order by the profile's rules, merchant enrichment, and the categorizer sub-agent on the fast slot with a confidence score per row. Every row gets an enriched title and short description. Confident rows are set. The Import page hands off to a new conversation where the assistant asks about the uncertain rows in Question cards: the transaction, the top guesses as buttons and a free text field, several rows per card. Each answer becomes a category rule so the same merchant never asks again. Telling the assistant "PayPal to Anna is always Dining" in plain language stores a rule too. Needs review remains the state of unanswered rows; Unknown is a real category never produced by automation.

**Blocked by:** 03 Data model, synthetic dataset and CSV import page, 05 Query sub-agent and the numbers invariant

**Status:** ready-for-agent

- [ ] Categorization pipeline with the three stages and a confidence threshold; batch calls to the categorizer sub-agent through a forced single tool returning category, subcategory, confidence and enrichment
- [ ] `ask_user` client-side tool: the agent emits a structured question, the frontend renders the Question card, the answer returns as tool output and the run continues
- [ ] Import page finishes by opening a conversation that summarizes the import and asks the questions
- [ ] Answers create category rules and apply to all matching rows in the profile; a rules stage runs before any model call
- [ ] Plain-language rule statements in chat create rules through a tool with a confirmation line
- [ ] HTTP-seam tests: rules beat the model, low confidence triggers a question, an answer becomes a rule that recategorizes matching rows
- [ ] Browser verification of import, questions, answers and the resulting table
