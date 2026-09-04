# 05: Query sub-agent and the numbers invariant

**What to build:** A user asks "how much did I spend on groceries in May" and gets a figure that came from a SQL query. The chat agent calls the query tool, a dedicated query sub-agent on the fast slot writes the SQL through a forced single tool, a guard validates it as a single read-only SELECT over the profile-scoped split-aware view with an automatic LIMIT, the rows come back, and the tool step in the transcript shows the SQL and the rows on expand. Follow-ups like "and compared to April" work. A profile without data gets a clear answer without any number. The system prompt forbids arithmetic in prose.

**Blocked by:** 01 Walking skeleton, 03 Data model, synthetic dataset and CSV import page

**Status:** ready-for-agent

- [ ] Query sub-agent prompt with schema, taxonomy, data date range and examples; same framing later reused for training
- [ ] SQL guard with sqlglot: single SELECT, allowlisted view, no writes or attach, auto LIMIT, clear error back to the agent for a retry
- [ ] Tool step UI shows the question the sub-agent received, the SQL, row count and a table of rows
- [ ] No-data path answers without calling the model for numbers
- [ ] HTTP-seam tests: scripted sub-agent SQL executes and its rows appear in the tool part; a write attempt is refused; empty profile answer
- [ ] Browser verification of three questions on the synthetic dataset including a follow-up
