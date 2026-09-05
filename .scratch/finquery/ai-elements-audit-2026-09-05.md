# AI Elements audit against FinQuery's UI

Date: 2026-09-05. Sources read: `.agents/skills/ai-elements/SKILL.md` and all 48 files under its
`references/`, the live registry index (`https://elements.ai-sdk.dev/api/registry/registry.json`,
136 items: 48 components plus 88 examples), and the per-component registry JSON of every one of
the 48 (the actual `.tsx` source, not only the docs page). On the FinQuery side: every file under
`frontend/src/components/`, the ten vendored components under `frontend/src/components/ai-elements/`,
`.scratch/finquery/spec.md` and `docs/demo-script.md`.

What we vendor today: `context`, `conversation`, `message`, `model-selector`, `prompt-input`,
`reasoning`, `shimmer`, `sources`, `suggestion`, `tool`. Five of those carry local edits
(see "Risks", "Re-running `add` overwrites our edits").

## The table

Value is about FinQuery specifically, not about the component. Effort assumes the component is
installed and wired into one place, with our copy and our theme tokens.

| Component | What it does (from its source) | Where in FinQuery | Value | Effort | Note |
| --- | --- | --- | --- | --- | --- |
| `agent` | Static config panel: `AgentHeader{name, model}`, `AgentInstructions`, `AgentTools` (accordion of an `ai` SDK `Tool` with its JSON input schema), `AgentOutput{schema}` | Settings, a "what the sub-agents are" explainer (query, chart, categorizer, extraction, memory, each with its slot and tools) | low | small | Not a runtime header: there is no `status` prop and no controls anywhere in the file. It cannot replace our tool cards (which are state-driven via `ToolHeader state=`) nor the turn chip. Pulls `accordion` and `code-block` (shiki). |
| `artifact` | Bordered container: header (title, description, actions, close) plus a scrolling content area | Chart card shell, in place of chart-tool.tsx's local `Card`/`Header` | low | medium | Lateral move. Our chart card is already this shape plus a `Footer` the component has no slot for. Would matter only if a chart ever opens full screen. |
| `attachments` | `Attachments{variant: grid\|inline\|list}` over `Attachment{data: FileUIPart & {id}, onRemove}`, with `AttachmentPreview` (real image thumbnails), `AttachmentInfo`, `AttachmentRemove`, `AttachmentHoverCard*` | Two places: composer.tsx's local `Attachments` chip row, and chat-view.tsx's `AttachmentChip` on a stored user message | **high** | small | The only adoption that changes what the audience sees. Demo step 12 drops a receipt photo: today the user message shows a grey icon plus a filename, with this it shows the receipt. Deps `ai`, `lucide-react`, `hover-card`, all already present. |
| `audio-player` | media-chrome player: play, seek, time, mute, volume | no fit | none | - | No audio anywhere in the spec or the demo. Pulls `media-chrome`. |
| `canvas` | `ReactFlow` preconfigured for AI node graphs | no fit | none | - | No graph UI. Pulls `@xyflow/react`. |
| `chain-of-thought` | Collapsible reasoning spine. `ChainOfThoughtStep{icon, label, description, status: 'complete' \| 'active' \| 'pending'}` on an icon rail with a connector line, plus `SearchResults`/`SearchResult` badges, `Content`, `Image` | Chart card details: the sub-agent's plan, query, draw, self-check and repair rounds, which today are `output.plan` prose plus an `output.notes` bullet list | **medium-high** | small | Do **not** wrap a whole turn in it: our query, chart and changeset cards are the audit trail and must not collapse behind one "Chain of Thought" toggle. Deps all present. |
| `checkpoint` | Icon plus a `Button` trigger plus a trailing `Separator`: a divider that restores the chat to a point | Considered for `summary-divider.tsx` and for changeset apply points; neither wins | low | small | The separator only renders *after* the children, so our centred pill would move to the left, and there is no content area, so the collapsible summary editor stays hand-rolled. Undo already sits on the changeset card, next to the rows it changed, which is better than a divider. |
| `code-block` | shiki highlighting, header with title and filename, actions, copy button, language selector, line numbers | no fit | none | small | We already ship one highlighter (`@streamdown/code` via `MessageResponse`), which is exactly why our vendored `tool.tsx` stubs `CodeBlock` out to a plain `<pre>` with a comment saying so. Adding shiki would be a second highlighter for the same SQL. |
| `commit` | Git commit: hash, message, author avatar, timestamp, changed files with +/- counts | no fit | none | - | No git surface. The changeset card is a diff of rows, not of file paths. |
| `confirmation` | `Alert` gated on the AI SDK approval state machine: `ConfirmationRequest`/`Accepted`/`Rejected`/`Actions`, returns `null` unless `approval` is set on the tool part | no fit | none | - | Strictly yes/no. Our Question card is a multi-row form (per-row option sets, per-row free text, "Skip these", "Send N answers", a server-written `Applied:` line) and our changeset has five statuses (proposed, applied, discarded, reverted, stale, superseded) served by `changesetQuery`, not by the tool part. We never use the SDK approval flow, so the component renders nothing without faking `approval`. |
| `connection` | An animated bezier connection line for React Flow | no fit | none | - | Pulls `@xyflow/react`. |
| `context` | Hover card over a token-usage ring, plus tokenlens-backed input/output/reasoning/cache breakdown and a cost footer | Already used, in `context-badge.tsx` | in use | - | We use `Context`, `ContextTrigger`, `ContextContent`, `ContextContentHeader`, `ContextContentBody` and **deliberately** dropped the rest (a 280-line diff against upstream): `usage`, `modelId`, `ContextInputUsage`/`OutputUsage`/`ReasoningUsage`/`CacheUsage`/`ContentFooter` and the `tokenlens` dep. Correct call: local llama.cpp and Gemma/Qwen have no meaningful tokenlens cost, and `ContextStats` carries no per-kind split. |
| `controls` | React Flow zoom and fit-view buttons | no fit | none | - | Pulls `@xyflow/react`. |
| `conversation` | `StickToBottom` wrapper, scroll button, empty state, **plus `ConversationDownload` and `messagesToMarkdown`** | Already used in chat-view.tsx; `ConversationDownload` is vendored and unused | **medium** (the download) | tiny | Zero install: the code is already in our tree. One button exports the chat as markdown. Pass a `formatMessage` or the default drops every tool step (it only reads `text` parts). |
| `edge` | Animated and dashed React Flow edges | no fit | none | - | Pulls `@xyflow/react`. |
| `environment-variables` | Masked name/value rows with a reveal `Switch`, copy buttons and a `required` badge | no fit today | low | medium | Closest real target would be a Settings "how this instance is configured" panel (provider, model dir, context budget). That panel does not exist, and we deliberately show no secrets. models-card.tsx's adapter path list is the only lookalike and it is three lines. |
| `file-tree` | Expandable folders and selectable files | no fit | none | - | Considered for taxonomy-card.tsx's category/subcategory tree and rejected: our subcategories are pills that each open a dropdown (rename, merge into, delete), which a file row cannot carry. Imports are a flat list, not a hierarchy. |
| `image` | Renders an `Experimental_GeneratedImage` (base64 from `generateImage`) | no fit | none | - | We never generate images. The bill photo is a user upload with a URL, which is `attachments`' job. |
| `inline-citation` | Citation pill whose label is `new URL(sources[0]).hostname`, opening a hover card carousel of `InlineCitationSource{title, url, description}` and `InlineCitationQuote` | no fit before Monday | low | large | Wrong data model for SQL provenance: ours is (turn, tool call, row), not a URL, so the trigger would need forking. Worse, nothing tags figures with spans today, and making a local Gemma E4B emit citation markers against the invariant "numbers always come from executed queries" risks a *wrong* citation on a number, which is worse than none. The Query step under the answer already carries the whole provenance. Would pull `carousel`. |
| `jsx-preview` | Evaluates a JSX **string** in the host page with `react-jsx-parser`, auto-closing tags while it streams | no fit, and actively wrong | none | - | Security note: we run model-written chart code in a cross-origin `sandbox="allow-scripts"` iframe with its own React and TanStack Charts bundle precisely so it cannot touch the app or the data. `jsx-preview` evaluates in the page and would dissolve that boundary. |
| `message` | `Message`, `MessageContent`, `MessageResponse` (Streamdown), `MessageActions`/`MessageAction`, `MessageToolbar`, and the `MessageBranch` family (one branch at a time with a `1 of N` selector) | Already used: `Message`, `MessageContent`, `MessageResponse`, `MessageToolbar` in chat-view.tsx, `MessageActions`/`MessageAction` for the thumbs in feedback.tsx | in use | - | `MessageBranch*` is vendored and unused, and should stay unused: our A/B pairs (`AnswerCompare`, and the chart Regenerate pair via `PairGrid`/`PairSide`) show **both** sides at once because the user has to compare them to pick, and they carry a "Pick this one" button and an `unavailable` state for a chart that did not draw. Branches would hide one side behind an arrow and have neither affordance. |
| `mic-selector` | Audio input device picker with permission handling | no fit | none | - | No voice in the product. |
| `model-selector` | cmdk command palette in a dialog | Already used, wrapped by `model-picker.tsx` | in use | - | One local edit: `defaultValue` forwarded to `Command` so the list opens on the slot in use. |
| `node` | Card-shaped React Flow node with handles | no fit | none | - | Pulls `@xyflow/react`. |
| `open-in-chat` | Dropdown that opens the query in ChatGPT, Claude, T3, Scira, v0, Cursor | no fit, and actively wrong | none | - | The exact opposite of the product's claim. Wiring an "open this in ChatGPT" button into a local-first app would undercut the privacy story on stage. |
| `package-info` | npm dependency name, version change, change-type badge | no fit | none | - | Not applicable. |
| `panel` | Positioned container on a React Flow canvas | no fit | none | - | Pulls `@xyflow/react`. |
| `persona` | Rive WebGL2 animated AI face with idle/listening/thinking/speaking/asleep states | no fit | none | - | A talking orb during a 96-second local chart turn works against a serious finance analyst, and it pulls `@rive-app/react-webgl2`. |
| `plan` | `Card` plus `Collapsible`, with `Shimmer` on the title and description while `isStreaming` | Chart card shell, or the "Planning, querying, drawing..." placeholder | low | medium | Lateral: chart-tool.tsx already composes Card, Collapsible and Shimmer by hand, and `PlanContent` wraps `CardContent`, which fights the full-bleed chart iframe. |
| `prompt-input` | Textarea, attachments with accept/size/count validation, tools row, submit and stop | Already used, in composer.tsx | in use | - | We keep our own rejection copy (`REJECTED`) because the library writes for many files at once. No local edits to the file itself. |
| `queue` | `QueueSection` (collapsible) plus `QueueSectionLabel{count, label, icon}`, `QueueList` (ScrollArea, max-h-40), `QueueItem`, `QueueItemIndicator{completed}`, `QueueItemContent` (line-through when done), `QueueItemDescription`, hover-revealed `QueueItemAction`s | `rule-tool.tsx` `ReviewToolStep`, the merchants still to be asked about, and `DuplicatesToolStep`'s pending count | medium | medium | A real fit for the *review queue*, not for the Question card (a `QueueItem` has no option buttons and no free-text field). Would give us a scrolling capped list for 25 merchants instead of a plain `<ul>`, and a strike-through as they get answered. Touches the demo spine (steps 4 and 5), so after Monday. |
| `reasoning` | Collapsible thinking panel with auto-open on stream, auto-close on finish and a duration line | Already used, in chat-view.tsx's `ThinkingPanel` | in use | - | We control `open` ourselves because the component closes itself exactly once, which broke a turn that thinks, calls a tool and thinks again. Local edit: streamdown plugins trimmed to `code`. |
| `sandbox` | Collapsible with a status header and Code / Output tabs, meant to pair with `code-block` and `stack-trace` | no fit | low | medium | Superficially the chart card (code plus rendered output), but our Details reads better as one scroll (request, plan, repairs, SQL, rows) than as two tabs, and it would pull `tabs` plus shiki. |
| `schema-display` | REST endpoint docs: method badge, path, parameters, request and response bodies | no fit | none | - | We have no HTTP docs surface. The adjacent idea (showing the transactions schema the SQL sub-agent is given) is a table schema, so `SchemaDisplayMethod` (GET/POST) and `SchemaDisplayPath` would be dead weight. |
| `shimmer` | Motion-driven text shimmer | Already used in five files | in use | - | No local edits. |
| `snippet` | `InputGroup` one-liner with a copy button | models-card.tsx's mono file and adapter paths | low | small | `input-group` is already installed. Our SQL is multi-line CTEs, so this is not the SQL copy button. |
| `sources` | Collapsible "Used N sources" with `Source` links | Already used, in lookup-tool.tsx | in use | - | One local edit: singular/plural in the trigger. |
| `speech-input` | Voice capture button, Web Speech API with a MediaRecorder fallback that posts audio to an external transcription service | no fit, and contradicts local-first | none | - | The Firefox/Safari fallback sends audio off the machine. |
| `stack-trace` | Parses JS and Node stack traces into frames, dims internal frames, collapsible, copy | no fit | none | - | Our failed-tool reason is one server-written sentence (`{tool_failed, error}` from `agent.guarded`), and a chart failure quotes SQL and the sub-agent's own comments (see `failureLine`), never a stack. It would parse zero frames. |
| `suggestion` | Row of clickable prompt chips | Already used, in empty-state.tsx and chat-view.tsx follow-ups | in use | - | No local edits. |
| `task` | `Collapsible` with `TaskTrigger{title}`, a left-rail `TaskContent`, `TaskItem` lines and `TaskItemFile` chips | no fit | none | small | Evidence against the docs: the docs page claims "visual icons for pending, in-progress, completed and error states" and a progress counter, and **the source has neither**, no status prop at all. import-tool.tsx's `Progress` already renders the same list *with* states (check for done, hourglass for current), so adopting `task` would be a downgrade for the long import. |
| `terminal` | ANSI console output with streaming and auto-scroll | no fit | none | - | Our import progress lines are user-facing sentences ("Reading the file..."). A terminal frame would make a friendly import look like a build log. Pulls `ansi-to-react`. |
| `test-results` | Summary counts, a progress bar, collapsible suites, per-test status, duration and error stack | `models-card.tsx` `CheckReport`, the `finquery-check` sanity report | low-medium | medium | A genuine shape match: per-check tick or cross, timings, a detail line, a pass/fail summary. Nice for the "green means the demo can start" beat, but Settings is not on the demo path. |
| `tool` | Collapsible tool-invocation card driven by `ToolUIPart['state']` | Already used in query-tool.tsx, import-tool.tsx, memory-tool.tsx, rule-tool.tsx | in use | - | Most edited of the ten (100-line diff): raw palette colours replaced with theme tokens, `CodeBlock` stubbed to a `<pre>`, radius and insets aligned with the rest of the transcript. |
| `toolbar` | React Flow `NodeToolbar` | no fit | none | - | Pulls `@xyflow/react`. Name collides with our `MessageToolbar`. |
| `transcription` | Click-to-seek transcript segments synced to playback | no fit | none | - | No audio. |
| `voice-selector` | Searchable voice picker with gender, accent and age metadata | no fit | none | - | No TTS. |
| `web-preview` | URL bar, back/forward/refresh, a sandboxed iframe body and a console log pane | no fit | low | medium | Our `ChartFrame` is already a sandboxed iframe with a postMessage protocol. A URL bar on a chart card is wrong, and the console idea is covered: we already show the frame's error over the chart and report it to the server for a retry. |

## Shortlist for Monday

Ranked. The first two are the only ones I would put in before the presentation, the third and
fourth are free (already in our tree).

### 1. `attachments`, in composer.tsx and chat-view.tsx

The only change on this list the audience will notice: demo step 12 drops
`bill-edeka-2025-03-14.png`, and today the user message shows a grey `FileTextIcon` and a
filename where the receipt itself could be.
It costs nothing to install: `attachments` needs `ai`, `lucide-react` and `hover-card`, all
already in the tree, and `usePromptInputAttachments().files` items are already
`FileUIPart & {id}`, exactly the `AttachmentData` shape the component takes.

```sh
cd frontend && npx ai-elements@latest add attachments
```

### 2. `chain-of-thought`, in the chart card's details

The chart sub-agent's plan and its repair rounds are the most interesting thing the app does and
today they are prose in a `<p>` and an unstyled `<ul>` under "Repairs"; as steps with
`status="complete" | "active" | "pending"` on an icon rail they read as work, which is what the
demo script asks the audience to look at ("the plan, the data line, Self-check passed").
Deps are all present (`@radix-ui/react-use-controllable-state`, `badge`, `collapsible`), and it
goes inside one card, so nothing in the transcript's spine moves.

```sh
cd frontend && npx ai-elements@latest add chain-of-thought
```

### 3. `ConversationDownload` (no install: already vendored, unused)

`frontend/src/components/ai-elements/conversation.tsx` already exports `ConversationDownload` and
`messagesToMarkdown`; wiring the button into `PageBar` next to the context badge is a handful of
lines and gives the demo a closing beat that lands with this product in particular ("and the
whole audit trail exports").
Pass a `formatMessage` that keeps the tool steps: the default reads `text` parts only, so a
straight adoption would export the answers and silently drop every query, chart and changeset.

### 4. `MessageBranch*` and `agent`: explicitly do not adopt

Listed here because both look like matches and are not. `MessageBranch` shows one branch at a
time, and every A/B in this app exists so the user can *compare* two outputs side by side and
press Pick. `agent` has no status and no controls, so it cannot carry a sub-agent step.

### 5. After Monday: `queue` in `ReviewToolStep`, `test-results` in the models card

```sh
cd frontend && npx ai-elements@latest add queue
cd frontend && npx ai-elements@latest add test-results
```

`queue` touches the conversation the demo opens on (steps 4 and 5), so it is not a Sunday change.
`test-results` is Settings, off the demo path, and worth it only if the sanity report is ever
shown to someone other than us.

## What we render by hand that a component would replace

| Hand-rolled | Where | Component | Verdict |
| --- | --- | --- | --- |
| `Attachments` chip row (about 40 lines: icon, truncated name, remove button) | `composer.tsx` | `attachments`, `variant="inline"` | replace, and gain an image thumbnail plus a hover card |
| `AttachmentChip` (about 18 lines) | `chat-view.tsx` | `Attachment` plus `AttachmentPreview` plus `AttachmentInfo` | replace, and gain the receipt thumbnail |
| `output.plan` paragraph plus the "Repairs" `<ul>` | `chart-tool.tsx` `Footer` | `chain-of-thought` steps | replace |
| No transcript export at all | `chat-view.tsx` `PageBar` | `ConversationDownload` (already vendored) | add |
| `Progress` ordered list with check and hourglass icons | `import-tool.tsx` | `task` | **keep ours**: `task` has no status prop at all |
| `SummaryDivider` trigger row | `summary-divider.tsx` | `checkpoint` | **keep ours**: no content area, and the pill would move off centre |
| `QuestionCard` (273 lines) and the changeset Apply/Discard | `question-card.tsx`, `changeset-card.tsx` | `confirmation` | **keep ours**: `confirmation` is yes/no and needs an SDK `approval` we never set |
| Review queue `<ul>` of merchants | `rule-tool.tsx` `ReviewToolStep` | `queue` | replace, after Monday |
| `CheckReport` tick/cross check list | `models-card.tsx` | `test-results` | optional, after Monday |
| SQL fenced through `MessageResponse` | `query-result.tsx` `SqlSection` | `code-block` | **keep ours**: a second highlighter (shiki) for the same SQL. Add a 10-line copy button instead |
| `Thumbs`, `MessageToolbar`, `Tool`, `Sources`, `Suggestion`, `ModelSelector`, `Shimmer`, `Reasoning`, `Context` | across the app | already AI Elements | nothing to do |
| Virtualized grid, click-to-edit cells, filter and bulk bars, sidebar chat list, tab strip, onboarding wizard bar, split editor, taxonomy pills, outbound log, imports list | transactions and settings pages | nothing in the registry | genuinely ours, and correctly so |

## Risks

**Re-running `add` overwrites our edits.** The CLI writes straight to
`src/components/ai-elements/<name>.tsx`. Five of our ten vendored files carry local changes that a
re-run would silently revert:

| File | Diff vs registry | What we would lose |
| --- | --- | --- |
| `context.tsx` | ~280 lines | the whole tokenlens removal, and our slot/memories/summarized-turns body |
| `tool.tsx` | ~100 lines | theme tokens instead of `text-green-600` and friends, the `CodeBlock` stub, radius and insets |
| `message.tsx` | ~47 lines | `group-[.is-assistant]:w-full` (without it every card resizes when a step opens), `tableMaxHeight={0}`, the trimmed streamdown plugins |
| `model-selector.tsx` | ~24 lines | `defaultValue` on `Command`, so the palette opens on the slot in use |
| `reasoning.tsx` | ~23 lines | the trimmed streamdown plugins |
| `sources.tsx` | ~13 lines | "1 source" instead of "1 sources" |

Rule: only ever run `add` for a component we have **not** vendored. If one of the six above must
be refreshed, diff first (`curl -s https://elements.ai-sdk.dev/api/registry/<name>.json | jq -r
'.files[0].content'` and `sed 's|@/registry/default/ui/|@/components/ui/|g'`).

**Bundle size.** The two recommended adoptions add **zero new npm dependencies** and zero new
shadcn primitives: `attachments` needs `ai`, `lucide-react` and `hover-card`, `chain-of-thought`
needs `@radix-ui/react-use-controllable-state`, `badge` and `collapsible`, all present. What the
rest would drag in, for the record: `@xyflow/react` (canvas, panel, node, edge, controls,
connection, toolbar), `shiki` (code-block, and transitively agent, tool, sandbox) on top of the
`@streamdown/code` highlighter we already ship, `@rive-app/react-webgl2` (persona),
`media-chrome` (audio-player), `ansi-to-react` (terminal), `react-jsx-parser` (jsx-preview),
`tokenlens` (the full context), `embla-carousel-react` via shadcn `carousel` (inline-citation).
New shadcn primitives some would pull: `accordion` (agent), `tabs` (sandbox), `avatar` (commit),
`carousel` (inline-citation).

**Behaviour changes.** `attachments` only renders; every rule about what we accept
(`ACCEPT`, `MAX_FILES`, `MAX_FILE_BYTES`) and our own refusal sentences (`REJECTED`) live in
`prompt-input` and must stay there. Keep `usePromptInputAttachments`, swap only the chip markup,
or the composer silently starts speaking the library's English ("All files exceed the maximum
size.") in place of ours. The composer is on every demo step, so this change wants one pass
through the drop, the reject and the remove paths before Monday, not on Sunday night.

**Theme.** The registry writes raw palette colours in places (`text-green-600`, `text-yellow-600`,
`text-red-600` in the stock `tool.tsx`, `fill="#fff"` in `connection.tsx`). Anything we add needs
the same audit our `tool.tsx` already got: theme tokens, or it will not follow dark mode.

**Vite, not Next.** The prerequisites in `SKILL.md` name a Next.js project, but nothing in the two
recommended files needs it: no `next/image`, no `next/link`, no server components. Our
`components.json` already sets `"rsc": false` and the aliases the CLI rewrites into
(`@/components`, `@/components/ui`, `@/lib/utils`), and `tsconfig` maps `@/*` to `./src/*`, so
`add` lands in the right place. Every registry file opens with `"use client"`, which Vite ignores;
it is noise, not a problem. One thing to check after any install: the registry sources import from
`@/registry/default/ui/...` and rely on the CLI to rewrite that path.

**Timing.** The demo's spine is the chat transcript: the Question card (steps 4 and 5), the query
step (6 to 8), the chart card (9, 10, 19), the changeset (11), the bill split (12). `attachments`
touches the composer and the user message, `chain-of-thought` touches one card's details. Nothing
else on this list should be touched before Monday, and `queue`, `test-results`, `agent` and
`snippet` are explicitly after it.
