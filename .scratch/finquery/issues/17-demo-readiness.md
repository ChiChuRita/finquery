# 17: Demo readiness

**What to build:** The full demo script runs on the local provider from a clean checkout without a reload or a crash: create a profile, import the synthetic CSV and PDF, answer the categorization and duplicate questions, ask three questions with a chart, split a transaction from a bill photo, show memory carrying into a second conversation, switch models, stop a generation, cross the compression threshold, rate a chart pair, look up a merchant on the web. The UI gets a final design pass so every screen looks like one product.

**Blocked by:** 02, 03, 04, 05, 06, 07, 08, 09, 10, 11, 12, 13, 14, 15, 16

**Status:** ready-for-agent

**Model note:** the design pass is done by Fable 5.1 as the user asked.

- [ ] Written demo script with timings in the repo
- [ ] Clean-checkout run: `uv sync`, `uv run finquery`, first-run downloads, full script completed on local models
- [ ] Design pass across chat, Transactions, Import, Settings, Memory, Feedback in both themes; consistent spacing, typography, empty states, loading states
- [ ] All HTTP-seam tests green; smoke suite green on local
- [ ] Browser verification of the whole script with screenshots
