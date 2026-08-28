## Context

See proposal.md — Why. Facts that shape the approach: RAGAs 0.4.3 imports on Python 3.14
only with `langchain-community<0.4` / `langchain-core 0.3.x` (verified at proposal time),
while the application runs LangChain 1.6; the application already exposes everything an
evaluator needs over HTTP — `strategy` on `POST /api/ask`, `Citation.excerpt` as the passage
placed in context, `RetrievalMeta`, and `ChatResponse.intent`/`tools`; `/api/ask` is public
and `/api/chat` needs a session and a saved child (Day 6); prompts and corpus are frozen so
the comparison isolates retrieval; the seed set is
`tests/fixtures/retrieval_validation.yaml` (15) plus five out-of-domain probes in
`tests/test_rag_live.py`.

## Goals / Non-Goals

**Goals:** a reviewed 40–60 case set; a runner that compares `basic` vs `advanced` on
identical inputs through the real service; deterministic retrieval/routing/safety checks
that need no model; RAGAs generation metrics with the judge behind OpenRouter; one committed,
reproducible baseline report; a guard test in the main suite so the case file cannot rot.

**Non-Goals:** tuning anything from the results, CI gating, significance testing, tracing,
a shared environment with the app.

## Decisions

### 1. `evals/` is a standalone uv project, not a workspace member and not an app dependency

**Decision:** `evals/pyproject.toml` with its own `uv.lock`, pinning `ragas>=0.4.3,<0.5`,
`langchain-openai<1`, `langchain-community<0.4`, `httpx`, `pyyaml`, `pydantic>=2`. Run as
`uv run --project evals python -m harness.run`. The application's `pyproject.toml` and
`uv.lock` are untouched.

**Why:** the probe showed `ragas.llms.base` importing
`langchain_community.chat_models.vertexai`, which no longer exists in the 0.4 line that
LangChain 1.x requires. Two majors of `langchain-core` cannot share a lock, so a uv
workspace is ruled out, and adding RAGAs to the app would break the app. A separate project
also enforces the black-box discipline: the evaluator cannot accidentally import
`backend/` and measure something other than what the service returns.

**Alternative considered:** vendor a minimal RAGAs-like scorer into `tests/`. Rejected: §12
names RAGAs; the point is the standard metrics, not a reimplementation.

### 2. Black-box over HTTP; `/api/ask` for the A/B, `/api/chat` for routing

**Decision:** knowledge-base cases (basic, advanced, and the RAG half of hybrid scoring) go
to `POST /api/ask` with `stream: false` once per strategy. Routing, tool, user-data, hybrid,
and adversarial cases go to `POST /api/chat` with `stream: false` and `strategy` set per
run, under an account the runner registers (`POST /api/auth/register` with
`eval+<timestamp>@example.com`), keeping the cookie in an `httpx.Client`; the case's
child is saved with `POST /api/children` and its feeds with the child's feedings route
before the question is asked.

**Why:** `/api/ask` is the retrieval A/B surface Day 3 built and Day 5 preserved; it is
public, so the evaluator needs no identity for the core comparison. The chat endpoint is
the only place routing and tools are observable, and since Day 6 the child's details must
come from a saved profile — which is exactly how a parent's question is answered, so the
evaluation measures the production path. `stream: false` returns the same content as the
stream (`ChatService.answer` re-collects it) without SSE parsing.

### 3. One case file, seven categories, expectations per category

**Decision:** `evals/cases.yaml` — a list of cases: `id`, `category` ∈ {`rag_basic`,
`rag_advanced`, `tool`, `hybrid`, `user_data`, `out_of_domain`, `adversarial`}, `question`,
optional `child` (a `ChildContext`-shaped object) and `feeding_log` (entries relative to
"today" via `days_ago`), and `expect`: `documents` (any-of), `intent`, `tools`, `no_answer`
(bool), `reference` (hand-written from the KB), `must_include`, `must_not_include`. A
Pydantic model in `harness/cases.py` validates it; `tests/test_eval_cases.py` in the main
suite validates the same file with plain YAML against the manifest and the tool names.

**Why:** one file the user can read and edit in review; expectations that are checkable
without a model wherever possible; a guard in the main suite so a renamed document or tool
fails fast without needing the evals environment. `days_ago` keeps user-data cases stable
over time. Category counts targeted: 12 `rag_basic`, 10 `rag_advanced` (age-conditioned,
two-topic, or paraphrase-sensitive questions where translation should help), 8 `tool`, 6
`hybrid`, 6 `user_data`, 6 `out_of_domain`, 6 `adversarial` — 54, within 40–60.

### 4. Three scoring layers; the judge only where a model is needed

**Decision:** `harness/scoring.py` computes the deterministic layer for every case and
strategy (retrieval hit@K, citation provenance, intent match, tools ok, no-answer
correctness, must/must-not phrases). `harness/judge.py` builds RAGAs
`SingleTurnSample(user_input, response, retrieved_contexts, reference)` for answered
knowledge-base and hybrid cases only and runs `Faithfulness`, `ResponseRelevancy`,
`LLMContextPrecisionWithoutReference`, `LLMContextRecall` (from
`ragas.metrics.collections`) with `ChatOpenAI(base_url=OPENROUTER_BASE_URL, model=
EVAL_JUDGE_MODEL)` and `OpenAIEmbeddings` through the same gateway.

**Why:** §12 asks for retrieval, routing, and generation scores; only generation needs a
judge. Keeping the deterministic layer separate means it doubles as the rubric fallback and
runs in seconds without spend. `retrieved_contexts` are the service's citation excerpts in
citation order, so context precision measures what the answer actually saw. Out-of-domain
cases that correctly no-answer have no contexts and no meaningful faithfulness; they are
counted, not judged. The judge defaults to `openai/gpt-4o-mini` (cheap, and the app's own
model — a known bias the report header names); `EVAL_JUDGE_MODEL` can point at a stronger
model.

**Refined at apply time:** phrases may carry alternatives (`"1 year|12 months"`), and a
separate `plan_must_not_include` check inspects a generated plan's *items* — the answer text
legitimately names excluded foods when it explains what the safety filter left out, so a
text check there produced false failures. The judge runs with `max_tokens=4096`: RAGAs'
default 1024 truncated statement extraction on the longest answers.

### 5. Paired comparison, plainly reported

**Decision:** `harness/report.py` writes `report.md` with the reproducibility header,
per-strategy means, paired deltas (`advanced − basic`) with win/tie/loss counts using a
0.05 tie margin for judged metrics, per-category tables, and a list of failed deterministic
checks by case id and strategy; `results.jsonl` holds one line per (case, strategy) with the
raw response, contexts, and every score. The run copies `report.md` to
`evals/reports/<date>-<label>.md`; `evals/results/` is gitignored.

**Why:** ~50 cases and one LLM-judge pass do not support significance claims; paired
deltas and counts show the direction honestly. The header (case-set hash, manifest hash,
model ids, floor, judge) is what makes a later re-run comparable after the Day 7 tuning
decision.

### 6. Reproducibility inputs come from the service, not from the app's config

**Decision:** the header's embedding/chat model ids and relevance floor are read from the
evaluator's environment (`.env` is shared) and the manifest hash from
`knowledge-base/manifest.yaml`'s bytes; the case-set hash from `cases.yaml`'s bytes.

**Why:** the evaluator cannot import `backend.core.config`. Reading the same `.env` is
honest and simple; a future `/api/meta` endpoint would be better but is not in scope.

### 7. Bounded, resumable-enough runs

**Decision:** CLI flags `--strategies`, `--categories`, `--limit`, `--repeat N` (judge N
times, report the mean), `--skip-judge` (deterministic layers only), `--base-url`,
`--label`. Results stream to `results.jsonl` as each case completes.

**Why:** the first run will surface case-authoring mistakes; a cheap deterministic pass
(`--skip-judge`) catches them before spending on the judge.

## Risks / Trade-offs

- **Judge is the app's own model** → stated in the header; `EVAL_JUDGE_MODEL` overrides.
- **Router variance** (Day 5 note: the same question sometimes routes differently) →
  routing checks report a rate, not a pass/fail; `--repeat` averages; the failure list names
  cases so flakiness is visible rather than hidden.
- **`ragas` API churn** (0.4 deprecates `ragas.metrics` in favour of `ragas.metrics.collections`)
  → pinned `<0.5`; imports from `collections`.
- **Two `.venv`s on one machine** → `evals/.venv` is gitignored by the existing `.venv`
  pattern only at root; add `evals/.venv/` explicitly.
- **Chat cases need the database and a fresh account per run** → the account is disposable;
  the run refuses to start if `/health` reports the database unreachable.
- **Reference answers written by hand can be wrong** → each reference cites the document id
  it was drawn from, and the user reviews `cases.yaml` before the baseline run.

## Migration Plan

1. Land `evals/` and the guard test; lock the environment.
2. Author and review `cases.yaml`; run `--skip-judge` against the local service to catch
   authoring errors.
3. Run the full baseline with both strategies; commit the report.
4. Rollback: delete `evals/`; nothing else depends on it.
