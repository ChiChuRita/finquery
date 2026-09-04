# 15: Preference optimization

**What to build:** Every assistant answer has thumbs up and down. Every chart has thumbs and a Regenerate that draws a second chart for the same request so the user picks the better one. A thumbs down on an answer offers an A/B: a second answer at higher temperature to pick from. Every rating and pick is stored as a preference record with prompt, chosen, rejected, SQL and chart code. A Feedback page shows the records and exports a JSONL training set. A training folder holds the DPO export and a train script for the fast slot's adapters.

**Blocked by:** 06 Chart sub-agent and chart runtime

**Status:** done

- [x] Preference record entity and REST endpoints for rating and pairs
- [x] Thumbs on answers and charts using the message actions of AI Elements
- [x] Chart Regenerate producing a side-by-side pair with a pick
- [x] Answer A/B on thumbs down with a pick
- [x] Feedback page listing records with export
- [x] Training folder with DPO export and train script and a README; the script is runnable against the export but training is a later phase
- [x] HTTP-seam tests: rating stored, pair stored with chosen and rejected, export shape
- [x] Browser verification of rating, a chart pair and the Feedback page

## Comments

Done 2026-09-04. Structure for the next tickets:

- `src/finquery/preferences.py` is the domain half: `read_turn` (what a stored turn asked,
  answered, ran and drew), `answer_of`/`answer_side`/`chart_side`/`chart_prompt` (the two sides
  of a record), `store` (the upsert), `list_records`, `records_of_conversation`, `export_jsonl`.
  `src/finquery/api/preferences.py` is the REST half.
- **A record is about a turn, not about a message.** `persist_turn` now generates the turn id,
  writes it into the assistant message's metadata and returns it, and the chat endpoint puts it
  into the metadata chunk it already sends at the end of a turn. So the browser can rate the
  answer it just watched and the same id is on the message after a reload, with no extra
  endpoint and no client-side id matching. A chart is `(turn_id, target)` where `target` is the
  `chart` tool call id, which is why one turn can carry an answer rating and a rating per chart.
- **Only the click comes from the browser.** The prompt, the answer text, the tool outputs and
  the chart's plan, SQL and code are read server-side from the stored turn, so a record always
  says what really happened. The one exception is the second half of a pair (a regenerated chart,
  a second answer): it was never a turn, so the client sends it back and says which side won.
- **Honest sides.** A thumbs up fills `chosen`, a thumbs down fills `rejected`, a pick fills
  both. Both columns are nullable and `rating` (`up`, `down`, `pick`) says which case it is, so
  a DPO export is "the rows with both sides" and nothing has to be inferred. One row per
  `(turn_id, target)`: clicking down after up is the user correcting themselves, not two clicks.
- Endpoints, all profile-scoped and all refusing another profile's turn with a 404:
  `GET /api/preferences`, `GET /api/preferences/export` (JSONL attachment),
  `POST /api/preferences/rating` (`turn_id`, optional `target`, `up`/`down`),
  `POST /api/preferences/pair` (`picked: original|candidate` plus the candidate),
  `POST /api/preferences/chart-alternative` (`turn_id`, `tool_call_id`),
  `POST /api/preferences/answer-alternative` (`turn_id`).
  `GET /api/conversations/{id}` gained `ratings`, so a reloaded transcript shows the thumbs.
- **Neither rerun is a chat turn.** Nothing is appended to the conversation, no follow-ups run
  and nothing is distilled. `chart-alternative` calls `run_chart` with the stored request and
  hints on the fast slot with `subagent_settings`, exactly as the tool does. `answer-alternative`
  runs `chat_agent` with `chat_agent.override(tools=[query], toolsets=[])`, so the only tool left
  is the read-only one: no changeset, no rule, and no `ask_user` (which would park the run
  waiting for a human). A turn that used one of those four is refused with a 409 and the UI does
  not offer the A/B for it either. Temperature 1.2 (`AB_TEMPERATURE`) is the only other
  difference from the turn it reruns.
- Frontend: `components/feedback.tsx` holds `useFeedback` (thumb and pick against one target),
  `useAnswerFeedback` (adds the A/B), `Thumbs` (AI Elements `MessageActions`/`MessageAction`),
  `PairGrid`/`PairSide` (two outputs, a Pick each) and `AnswerCompare`.
  `chat-view.tsx` puts the thumbs in the message toolbar and the compare view under it;
  `chart-tool.tsx` replaced the ticket 06 rating placeholder with the real thumbs plus
  Regenerate and renders the pair as two frames side by side.
  `components/feedback-page.tsx` is `/feedback` (kind, rating, prompt excerpt, date, slot, and
  the Export button as a plain download link).
- The chart sub-agent sometimes writes the **same definition twice**. Two identical charts are
  nothing to pick between and such a pair teaches a training run nothing, so the card says "Same
  chart again" instead of opening a pair, and `export_pairs.py` drops a pair whose sides are
  equal anyway. Regenerate can simply be pressed again.
- `training/preference/`: `export_pairs.py` reads the database and writes
  `data/chart.jsonl` (prompt = request, plan and SQL; sides = the two definitions) and
  `data/query.jsonl` (prompt = the question; sides = two statements, which is what an answer A/B
  leaves behind when both runs queried). `train_dpo.py` is TRL's `DPOTrainer` on
  `google/gemma-4-E4B-it` in 4-bit with a rank-16 LoRA, reference-free because the base weights
  are the reference; `--dry-run` validates a dataset and imports neither torch nor trl, so it
  runs on the laptop. `README.md` is the loop end to end, including the GGUF conversion the
  adapter registry needs (`models/adapters/{query,chart}.gguf`).
- Tests: `uv run pytest` is 98 passed, 2 skipped (`tests/test_preferences.py` adds 8). It reuses
  `scripted_chart` and `ask_chart_then_report` from `test_chart.py` and `call_tools` from
  `test_categorization.py`. Requests per turn are unchanged; a chart regenerate costs the fast
  slot one plan, one statement and one code, and an answer A/B one chat request with only
  `query` declared (the test asserts both the tool list and the temperature).
- Verified on OpenRouter on port 8082 with a throwaway database and the shipped Sparkasse year
  (433 rows, categorized): a thumbs up on "Wie viel habe ich 2025 fuer Lebensmittel ausgegeben?"
  (4474,95 EUR), a thumbs down on the subscriptions answer followed by "Compare a second answer"
  and a Pick, a monthly line chart regenerated into a second frame side by side and picked, a
  reload showing the filled thumb, "Pair collected" on the answer and on the chart card, the
  Feedback page listing all three records with the export count, and the Export button writing a
  three-line JSONL. `export_pairs.py` over that database produced one query pair (the two A/B
  runs wrote different SQL) and no chart pair, because the two chart definitions were identical.
  Screenshots: /tmp/finquery-15/.
- Seen in passing, not from this ticket: the fast model on OpenRouter sometimes ends its answer
  with a stray `<turn|>` marker (visible in the transcript and therefore in a stored side), and
  the memory distillation pass logs `Please include your response in a tool call` when the model
  answers it in prose. Both are pre-existing.
