# 01: Walking skeleton

**What to build:** A user runs `uv run finquery`, opens the browser, and chats with the assistant in a modern AI Elements interface. The assistant runs on the OpenRouter fast slot, its thinking streams live into a collapsible reasoning panel that folds when the answer starts, the answer renders as markdown, Stop cuts generation and keeps the partial turn, and conversations persist for a default profile across reloads. This is the tracer bullet every other ticket hangs off: one Python process, SQLite, Pydantic AI, the Vercel AI SDK stream adapter, Vite plus React plus AI Elements, and the HTTP-seam test harness with the scripted FunctionModel.

**Blocked by:** None (can start immediately)

**Status:** done

**Model note:** the frontend shell sets the look of the whole app; the user asked for the UI to be built by Fable 5.1 with AI Elements used wherever a component fits.

- [x] `uv run finquery` starts one process that serves the API and the built frontend; a dev mode runs Vite with a proxy
- [x] Two model slots (fast, quality) resolved by a provider env var; openrouter maps to Gemma 4 26B-A4B and 31B with reasoning enabled; local is a stub that raises a clear not-yet-available error
- [x] Chat endpoint speaks the AI SDK UI message stream (sdk_version 7, correct headers, reasoning parts, text parts, finish); the frontend uses useChat with the default transport
- [x] A dedicated stop endpoint cancels the running generation; the partial turn is persisted and marked interrupted
- [x] Conversations and messages persist in SQLite under a default profile; reload restores the transcript
- [x] UI: conversation, message with markdown, reasoning panel with duration, prompt-input with stop, model selector showing fast and quality, dark and light theme, empty-state suggestions
- [x] Test harness: async HTTP client against the app, both slots replaced by a scripted FunctionModel, first tests assert the stream order (reasoning, text, finish) and persistence
- [x] CONTEXT.md with the glossary from the spec, ADRs for: Pydantic AI plus Vercel adapter, provider switch with two slots, single HTTP test seam, numbers only from executed queries
- [x] Browser verification with screenshots of a full chat turn in both themes

## Comments

Done 2026-09-04. Skeleton structure for the next tickets:

- Backend: `src/finquery/app.py` (`create_app(settings, resolve_model=..., serve_frontend=...)`),
  `providers.py` (slots, `build_resolver`), `db.py` (Profile, Conversation, Turn),
  `api/conversations.py` (REST), `api/chat.py` (AI SDK stream, stop, turn persistence).
- A turn row stores `model_messages_json` (Pydantic AI history) and `ui_messages_json` (AI SDK UI
  messages), plus `model_slot` and `interrupted`. Turn-level facts live in the assistant UI
  message metadata (`interrupted`, `thinking_seconds`).
- Frontend: `frontend/src/routes.tsx` (`/` and `/c/$conversationId`), `components/chat-view.tsx`
  (useChat), `components/composer.tsx`, `components/model-picker.tsx`, `components/app-sidebar.tsx`.
- Tests: `tests/conftest.py` fixtures `client`, `scripts` (per-slot FunctionModel stream
  functions), `chat`. 7 tests.
- Screenshots of the verification: /tmp/finquery-01/.
