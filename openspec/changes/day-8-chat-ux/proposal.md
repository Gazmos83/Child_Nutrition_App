## Why

Reference §17 gives Day 7 to "Deployment + UX polish"; with both services live, this is the
UX-polish workstream — specifically the part that does not depend on the visual mock-up that
is still to come. Three defects ship to users today: every coverage and nutrient-gap bar
draws twice (`ui/progress.tsx` renders its own track *and* the caller's), the app renders in
the browser's default font because `--font-sans: var(--font-sans)` in `globals.css` is a
self-reference that never resolves (Geist is downloaded and never applied), and the router's
`planned` list — every capability chosen, streamed before any tool runs — is stored by the
reducer and read by nothing, so the chat looks idle exactly when it is working. Two more
behaviours read as broken: the answer prompts instruct the model to use bulleted lists, and
the UI renders them as literal hyphens under `whitespace-pre-wrap`; and the message list
calls `scrollIntoView` on every token, yanking the view to the bottom whenever a parent
scrolls up mid-answer. The tool-activity display also shows parents raw
`JSON.stringify(args/result)` as its only detail view.

**Scope: [MVP]** — §2 requires tool-activity indicators and citations in a production UI,
and the chat-ui spec requires tool outcomes a parent can act on. Developed on `main`;
each group is independently shippable since Vercel deploys on push.

## What Changes

- **Progress bars render once.** `ui/progress.tsx` renders the caller's children *or* its
  default track, never both. Regression guards in both card tests assert exactly one track
  per nutrient row.
- **The sans font actually applies.** `--font-sans` maps to `--font-geist-sans` (the
  variable `layout.tsx` defines), mirroring the already-correct `--font-mono` line.
- **Planned tool steps are visible work.** A pure `src/lib/tool-steps.ts` merges
  `message.planned` with arrived results by name (the backend reorders — planner last — and
  may run an implicit gap check that was never planned, so position cannot be trusted and no
  result may be dropped). Steps show as pending the moment routing lands, resolve to success
  or failure as `tool` events arrive, and demote to "didn't get to it" if the stream ends
  without them. `search_guidelines` never emits a `tool` event; its completion signal is
  `retrieval` arriving with `final`.
- **Tool activity reads as prose.** One line per step from a new `copy.toolSummary(name,
  args, result)` ("BMI from 8.4 kg and 68 cm", "Checked the last 5 days"), lucide status
  icons instead of `✓`/`✗` glyphs, context badges with a tooltip listing the fields, and the
  raw args/result JSON kept one click deeper behind the existing Show details toggle. The
  list wraps in a collapsible: expanded while streaming or when anything failed, collapsed
  behind a "What we used" toggle once a clean answer lands. Failure messages stay visible.
- **Answers render their markdown.** A ~70-line block parser (`src/lib/markdown.ts`) for
  exactly what the prompts ask — paragraphs, `-`/`*`/`1.` lists, `**bold**`, `` `code` `` —
  emitting a typed tree; no HTML is constructed from model output, and the parser is total
  on partial input so half-streamed markup renders as plain text until the next token.
  `[n]` citation splitting runs on every leaf text run, so markers anchor identically inside
  list items and bold text; `answer-text.tsx` keeps its `#src-{messageId}-{n}` contract with
  `citations.tsx`.
- **Streaming respects the reader.** The message list tracks whether the parent is within
  64px of the bottom; only then does a new token scroll the view. Scrolled up, the view
  stays put and a sticky "Jump to the latest" button appears.

## Capabilities

### Modified Capabilities

- `chat-ui`: *Answers stream and show their provenance* — the provenance display now
  includes the planned steps as pending work before results arrive, prose summaries as the
  primary view with raw data on request, and disclosure rules (never collapse a failure);
  answer text renders light markdown with citation anchoring preserved. A new requirement
  covers scroll pinning during streaming.

## Impact

- **New code**: `frontend/src/lib/tool-steps.ts`, `frontend/src/lib/markdown.ts`, tests
  `tool-steps.test.ts`, `markdown.test.ts`, `tool-activity.test.tsx`, `answer-text.test.tsx`,
  `message-list.test.tsx`.
- **Touched code**: `ui/progress.tsx` (children-or-default), `app/globals.css` (one line),
  `components/chat/tool-activity.tsx` (rewrite), `components/chat/answer-text.tsx`
  (block rendering around the unchanged citation logic), `components/chat/message-list.tsx`
  (scroll pinning), `components/chat/assistant-message.tsx` (passes steps),
  `lib/copy.ts` (`toolSummary`, `TOOL_STEP_PENDING`, `TOOL_STEP_SKIPPED`, `JUMP_TO_LATEST`),
  `copy.test.ts` (`toolSummary` outputs added to the lint array), the copy snapshot,
  `src/test-setup.ts` (`scrollIntoView` stub), both card tests (track-count guards).
- **Untouched**: the backend entirely; `use-chat.ts`, `chat-reducer.ts`, `sse.ts`,
  `api-types.ts`; the `data-testid="tool-chip"` / `data-status` selectors; the disclaimer,
  override banner, exclusions, and no-safe-plan surfaces.
- **Dependencies**: none added. Icons come from the already-installed `lucide-react`;
  collapsible and tooltip were installed and unused.

## Non-goals

- **The visual redesign** — palette, semantic status tokens, dark-mode reachability, the
  mobile drawer, skeletons, empty-state art. All of it waits on the coming mock-up.
- **Conversation history and the dashboard** — real MVP gaps (§2, §6) but backend-touching;
  they get their own proposals.
- **Chat affordances** (typing indicator, copy-answer button, suggested starter prompts) —
  deferred with the visual pass.
- **A markdown library** — `react-markdown` would need a custom remark plugin to keep
  citation anchors and adds a sanitisation surface on LLM output; the prompts only ask for
  paragraphs, lists, bold, and code.
