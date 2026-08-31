Developed on `main`; frontend only, no backend or wire-type changes. Every group is
independently shippable (Vercel deploys on push). Verify for every group:
`pnpm -C frontend test && pnpm -C frontend typecheck && pnpm -C frontend lint &&
pnpm -C frontend build`.

## 1. Rendering fixes

- [x] 1.1 `ui/progress.tsx`: render `{children ?? <ProgressTrack><ProgressIndicator/></ProgressTrack>}`
  instead of children *and* the default track; add a track-count guard to
  `meal-plan-card.test.tsx` and `gap-report-card.test.tsx` (`[data-slot="progress-track"]`
  → exactly 3); verified the guards fail against the old code (6 tracks) and pass now
- [x] 1.2 `app/globals.css`: `--font-sans: var(--font-geist-sans)` replacing the
  self-reference; verified the compiled CSS emits `--font-sans:var(--font-geist-sans)` and
  no longer the cyclic declaration

## 2. Tool steps

- [x] 2.1 `src/lib/tool-steps.ts`: pure merge of `message.planned` with `message.tools` —
  match by name consuming the i-th occurrence (the backend runs the planner last and may add
  an implicit `detect_nutrient_gaps`), append unplanned results, `search_guidelines`
  completes on `retrieval`, leftovers demote from pending to skipped when the stream ends;
  verify `pnpm -C frontend exec vitest run src/lib/__tests__/tool-steps.test.ts`
- [x] 2.2 Copy: `toolSummary(name, args, result)` covering the eleven `TOOL_LABELS` names
  with guarded reads, `TOOL_STEP_PENDING`, `TOOL_STEP_SKIPPED`; add representative
  `toolSummary` outputs to the `RENDERED` array in `copy.test.ts` so the no-`!` lint covers
  them; refresh the snapshot and review the diff
- [x] 2.3 Rewrite `components/chat/tool-activity.tsx`: prose line per step, lucide status
  icons (spinner/check/triangle/dashed) with text carrying the meaning, context badges via
  `ui/tooltip`, raw JSON behind the existing Show details toggle, the list in
  `ui/collapsible` (open while streaming or failed, collapsed after a clean answer, parent's
  toggle wins); keep `data-testid="tool-chip"` and `data-status`; wire
  `assistant-message.tsx` to pass `toolSteps(message)`; verify
  `pnpm -C frontend exec vitest run src/components/chat/__tests__/tool-activity.test.tsx`
  (failed step stays visible, raw data reachable, clean run collapses and reopens)

## 3. Markdown answers

- [x] 3.1 `src/lib/markdown.ts`: typed block parser for paragraphs, `-`/`*`/`1.` lists,
  `**bold**`, `` `code` `` — markers need content so a dangling `- ` stays text; total on
  partial and pathological input; verify
  `pnpm -C frontend exec vitest run src/lib/__tests__/markdown.test.ts`
- [x] 3.2 `components/chat/answer-text.tsx`: render the block tree; the `[n]` MARKER split
  runs on every leaf text run (inside bullets and bold) and keeps the
  `#src-{messageId}-{n}` / `aria-label="Source n"` contract; verify
  `pnpm -C frontend exec vitest run src/components/chat/__tests__/answer-text.test.tsx`

## 4. Scroll pinning

- [x] 4.1 `components/chat/message-list.tsx`: track pinned-to-bottom
  (`scrollHeight - scrollTop - clientHeight < 64`) on scroll, autoscroll only when pinned,
  sticky "Jump to the latest" button otherwise (`JUMP_TO_LATEST` in copy); stub
  `Element.prototype.scrollIntoView` in `src/test-setup.ts`; verify
  `pnpm -C frontend exec vitest run src/components/chat/__tests__/message-list.test.tsx`

## 5. Live verification

- [ ] 5.1 After push, on the live URL: ask a question that routes to tools and see planned
  steps appear pending then resolve; an answer with a bulleted list renders as a list and
  its `[n]` markers jump to Sources; scroll up mid-stream and confirm the view stays put
  with the jump control offered; body text renders in Geist (devtools computed
  `font-family`); a meal-plan answer shows one coverage bar per nutrient
