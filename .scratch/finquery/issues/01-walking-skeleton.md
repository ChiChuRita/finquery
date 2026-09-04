# 01: Walking skeleton

**What to build:** A user runs `uv run finquery`, opens the browser, and chats with the assistant in a modern AI Elements interface. The assistant runs on the OpenRouter fast slot, its thinking streams live into a collapsible reasoning panel that folds when the answer starts, the answer renders as markdown, Stop cuts generation and keeps the partial turn, and conversations persist for a default profile across reloads. This is the tracer bullet every other ticket hangs off: one Python process, SQLite, Pydantic AI, the Vercel AI SDK stream adapter, Vite plus React plus AI Elements, and the HTTP-seam test harness with the scripted FunctionModel.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

**Model note:** the frontend shell sets the look of the whole app; the user asked for the UI to be built by Fable 5.1 with AI Elements used wherever a component fits.

- [ ] `uv run finquery` starts one process that serves the API and the built frontend; a dev mode runs Vite with a proxy
- [ ] Two model slots (fast, quality) resolved by a provider env var; openrouter maps to Gemma 4 26B-A4B and 31B with reasoning enabled; local is a stub that raises a clear not-yet-available error
- [ ] Chat endpoint speaks the AI SDK UI message stream (sdk_version 7, correct headers, reasoning parts, text parts, finish); the frontend uses useChat with the default transport
- [ ] A dedicated stop endpoint cancels the running generation; the partial turn is persisted and marked interrupted
- [ ] Conversations and messages persist in SQLite under a default profile; reload restores the transcript
- [ ] UI: conversation, message with markdown, reasoning panel with duration, prompt-input with stop, model selector showing fast and quality, dark and light theme, empty-state suggestions
- [ ] Test harness: async HTTP client against the app, both slots replaced by a scripted FunctionModel, first tests assert the stream order (reasoning, text, finish) and persistence
- [ ] CONTEXT.md with the glossary from the spec, ADRs for: Pydantic AI plus Vercel adapter, provider switch with two slots, single HTTP test seam, numbers only from executed queries
- [ ] Browser verification with screenshots of a full chat turn in both themes
