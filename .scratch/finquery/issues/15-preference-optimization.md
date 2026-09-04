# 15: Preference optimization

**What to build:** Every assistant answer has thumbs up and down. Every chart has thumbs and a Regenerate that draws a second chart for the same request so the user picks the better one. A thumbs down on an answer offers an A/B: a second answer at higher temperature to pick from. Every rating and pick is stored as a preference record with prompt, chosen, rejected, SQL and chart code. A Feedback page shows the records and exports a JSONL training set. A training folder holds the DPO export and a train script for the fast slot's adapters.

**Blocked by:** 06 Chart sub-agent and chart runtime

**Status:** ready-for-agent

- [ ] Preference record entity and REST endpoints for rating and pairs
- [ ] Thumbs on answers and charts using the message actions of AI Elements
- [ ] Chart Regenerate producing a side-by-side pair with a pick
- [ ] Answer A/B on thumbs down with a pick
- [ ] Feedback page listing records with export
- [ ] Training folder with DPO export and train script and a README; the script is runnable against the export but training is a later phase
- [ ] HTTP-seam tests: rating stored, pair stored with chosen and rejected, export shape
- [ ] Browser verification of rating, a chart pair and the Feedback page
