# 28: Onboarding for a new profile

**What to build:** A new profile opens with a short onboarding instead of an empty chat. The user picks which categories exist for them (the default taxonomy with subcategories shown as toggles, each category on or off, plus adding their own and renaming), sets the few preferences that shape the assistant (answer language: follow my message, German, or English; default model; web lookup on or off with its one-line privacy note), and gets their first data in (drop a statement or CSV here, which hands the file to a new chat where import and the Question cards happen, or load the shipped sample year to try things out). Finish lands in a chat with a short welcome that says what to ask first. Onboarding is skippable at every step, resumable, and reopenable from Settings. Requested by the user on 2026-09-05.

**Blocked by:** 24 (merged)

**Status:** done

- [x] Profile gains an onboarding state (not started, done, skipped); the first profile created at startup and every new profile start in not started; the app opens onboarding for a profile in that state and never again once done or skipped, with a Settings entry to reopen it
- [x] Step 1 Categories: the default taxonomy rendered as a toggle list with subcategories underneath, all on by default; the user turns categories off (they are removed from this profile's taxonomy), adds a category or subcategory, renames inline; Needs review and Unknown are explained in one line and are not toggles
- [x] Step 2 Preferences: answer language (follow my message, German, English) stored on the profile and read by the prompt; default model slot for new conversations; web lookup switch with the privacy note (only a scrubbed merchant token ever leaves, off by default)
- [x] Step 3 First data: a drop zone that accepts CSV, PDF and images and hands them to a new conversation exactly like dropping into the composer (so import, mapping confirmation, duplicates and Question cards all happen in chat), or a "Load the sample year" button that imports the shipped synthetic dataset through the same path, or Skip
- [x] Finish: a new conversation opens with a short welcome message seeded by the server (no model call), naming the profile's data state and three things to ask first
- [x] Skip and Back on every step; state saved per step so a reload resumes; keyboard reachable
- [x] Copy is plain and short; both themes; 1024 and 1440; the flow uses the shadcn and AI Elements primitives already in the app and follows the repo skills
- [x] HTTP-seam tests: onboarding state transitions, taxonomy toggles remove and add categories, preferences stored and read by the prompt (language rule), sample data import through the chat path, welcome turn seeded; typecheck, build and suite green; browser verification of the full flow in both themes

## Comments

Done 2026-09-05. `uv run pytest` is 164 passed, 4 skipped (the four are environmental: the two
private Trade Republic fixtures and the opt-in local smoke suite). `npx tsc --noEmit`,
`npm run build` and `oxlint` are clean (34 warnings, 31 pre-existing plus one each for
`onboarding.tsx`, `routes.tsx` and shadcn's `toggle.tsx`, all `only-export-components`).
Screenshots: `/tmp/finquery-28/`.

### What it is

`/onboarding` is a route with three steps and a finish, and the step is a search parameter, so a
reload resumes where the user was and Back is the browser's own button as well as ours. A profile
whose `onboarding_state` is `not_started` is redirected there from `/` once; Settings has a Setup
card that reopens it whether it was finished or skipped.

**Nothing in it is a second way to do something the app already does**, which is the whole design:

- **Step 1** renders the profile's real taxonomy. A toggle turned off proposes and applies a
  `taxonomy` changeset with `operation: "delete"`, the same two calls the Settings taxonomy editor
  makes; adding and renaming are the same path with `add` and `rename`. A row turned off keeps its
  place in the list, greyed, and turning it back on re-adds the category and the subcategories it
  had. After a reload it is simply gone, because the taxonomy is the truth. `Unknown` is filtered
  out of the toggle list and, with `Needs review`, explained in an `Alert` under it.
- **Step 2** is one `PATCH /api/settings` per control. Nothing new on the wire: the endpoint that
  had the web lookup switch now carries `onboarding_state`, `answer_language` and
  `default_model_slot` too, each optional, each a `Literal` so a wrong value is a 422.
- **Step 3** renders `components/composer.tsx` itself. A file dropped on it goes through
  `lib/pending.ts` into a new conversation with "Import this." as the first message, exactly what
  the empty page does, so the mapping confirmation, the duplicates and the Needs review questions
  all happen on Question cards in the chat.
- **Finish** opens the welcome conversation.

### Server

Two new endpoints, both seeding their turn with the module-level `persist_turn` the way
`imports/review-conversation` does, neither calling a model:

- `POST /api/onboarding/sample` creates a conversation, stores
  `fixtures/synthetic/sparkasse-2025.csv` as an attachment on it and runs
  `ingest.chat_import.import_attachment`, the same function the `import_file` tool calls. The
  seeded turn is the turn a dropped file produces: the user's line with the attachment chip, an
  `import_file` tool call and its result (so the transcript renders the real import step with the
  counted figures), the summary sentence, and the pending `ask_user` card. Answering that card
  resumes the run through the deferred path like any other, which the browser run confirmed.
- `POST /api/onboarding/welcome` writes one assistant turn from `load_query_context` (the count,
  the date range, the accounts) with three suggested questions as the `data-followups` part, so
  the existing chips render them. German when the profile chose German, English otherwise. There
  is no user message in it: nobody asked for it.

New columns through `db.NEW_COLUMNS` on `profile`: `onboarding_state` (`not_started`, `done`,
`skipped`), `answer_language` (`follow`, `de`, `en`) and `default_model_slot`. An existing
database gets `not_started`, so the first run after this merge opens onboarding, which is what
ticket 17's demo wants.

`src/finquery/onboarding.py` is the one place that knows the copy: the welcome text, its three
questions and `language_rule`. `agent.answer_language` is a dynamic instruction next to
`data_brief` that returns that rule, empty for `follow`. The prompt's own rule is "answer in the
language of the newest message", so a fixed choice has to say it overrides it, and it does.

### Numbers

- The system prompt is unchanged at 2560 tokens. The answer-language block is 51 tokens and only
  for a profile that fixed its language, so `tests/test_context.py` BUDGET stays at 4000; the
  comment there carries both numbers.
- Requests per turn are unchanged. The sample import costs what any import of that file costs
  (one categorizer call for what the dictionary could not place); the welcome costs none.
- Seven new tests in `tests/test_onboarding.py`, one per acceptance item: the state transitions
  and their 422, the taxonomy toggles through the changeset path, the preferences with the German
  rule appearing in the next turn's prompt and disappearing again, the sample year (433 rows, the
  import record's `conversation_id`, the chip, the tool part, the pending card), the welcome for
  an empty profile, the welcome for a full one in German, and ownership.

### Verified headful on OpenRouter, port 8095, throwaway database, session `onboarding`

A new profile ("Household") created from the switcher landed straight in onboarding.

- **Step 1**: Health and Education turned off (both really gone from
  `GET /api/categories`), Education's row stayed in place and greyed, "Pets" added with a "Vet"
  subcategory, "Communication" renamed and renamed back inline. `01` to `03`
- **Step 2**: Deutsch and Gemma 4 E4B chosen, web lookup switched on and off again, each one
  read back from `GET /api/settings`. Arrow keys move the roving focus and Space selects, with a
  visible focus ring. `04`, `22`, `25`
- **Step 3, sample year**: 20 seconds from the click to the chat, which shows "Import this." with
  the `sparkasse-2025.csv` chip, the import step reading "Imported 433 bookings", the counted
  summary and the five-merchant card. Answering two rows applied both rules ("7 bookings
  recategorized" each) and the model answered **in German** in an otherwise English conversation,
  which is the language rule doing its job in the product. `06` to `09`
- **Step 3, dropped file**: a CSV dropped on the composer (a synthetic `drop` event carrying the
  file, the way a real drag and drop does) opened a new conversation whose first message is
  "Import this." with the chip, and the assistant imported 5 of 5 bookings. `14`, `15`
- **Reopen and skip**: Settings → Setup → "Run setup again" reopens at step 1; "Skip setup"
  writes `skipped` and lands on the empty page, and the redirect does not fire again. `10`, `16`
- **Reload mid-flow** on step 2 came back on step 2 with Deutsch still selected.
- **Finish**: the welcome names "433 Buchungen von 01.01.2025 bis 28.12.2025 in Sparkasse
  Girokonto" with three German suggestions; clicking one ran a real turn (query step, German
  answer, its own follow-ups). A third profile walked end to end with English and the quality slot
  got the English welcome for an empty profile, on Qwen3.5 9B. `12`, `13`, `21`, `26`
- **Both themes at 1024 and 1440**: `17` to `20` and `23`, `24`.
- Zero browser console messages, zero page errors and no server-side error for the whole session.

### Seen in passing, for other tickets

- The literal `thought ` in front of one answer is still there (ticket 24 saw it too).
- The one axe violation on the page is `aria-required-children` on the conversation tab bar
  (`role="tablist"` holding a link and a button), which predates this ticket.

### For ticket 17

The demo now starts with onboarding: a fresh database opens `/onboarding` instead of the empty
chat. The script should either walk it (categories, German or English, the sample year) or press
Skip setup before the first question, and it can no longer assume `/` is the first screen. "Load
the sample year" is now the fastest way to get the fixture in: one click, no curl, and it leaves
the same review card the demo answers.
