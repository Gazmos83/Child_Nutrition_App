## Why

Reference §12 commits the MVP to A/B testing the two retrieval strategies — `basic` (single
query, top-K) and `advanced` (age extraction → metadata filter → query translation →
multi-query fusion) — with RAGAs where practical, over a 40–60 case test set covering
basic RAG, advanced RAG, tool questions, RAG+tool combos, user-data questions,
out-of-domain, and adversarial inputs, scoring retrieval, routing, and generation. Day 3
built both strategies behind one shared prompt precisely so this comparison would isolate
retrieval; Day 5 froze prompts and the corpus for the same reason; today's logging change
left `/api/ask` public so an evaluator can hit it without a session. Nothing evaluates
anything yet: the only test set is `tests/fixtures/retrieval_validation.yaml` (15
questions, top-3 recall), and no score has ever been produced for generation quality.

A probe at proposal time settled the one open technical question: RAGAs 0.4.3 installs and
imports on Python 3.14, but only with `langchain-community<0.4` / `langchain-core 0.3` —
which cannot coexist with the application's LangChain 1.6 stack. The evaluator therefore
lives in its own environment and treats the running service as a black box.

**Scope: [MVP] "committed hard bonus task" (§12). Day 6 of 7, third workstream, after
`day-6-logging-and-monitoring` (archived).** Time-box: half a day for the harness and the
test set; the baseline run itself is a few minutes of wall-clock and cents of model spend.
Additive; developed on `main`. Prompts, corpus, retrieval behaviour, and the API are not
changed by this work — it measures them.

## What Changes

- **A standalone evaluation project, `evals/`** — its own `pyproject.toml` and `uv.lock`
  (RAGAs 0.4.3, `langchain-openai<1`, `langchain-community<0.4`, `httpx`, `pyyaml`,
  `pydantic`), run with `uv run --project evals`. Not a workspace member: a workspace shares
  one lock and could not hold two `langchain-core` majors. It never imports `backend/`.
- **A 40–60 case test set, `evals/cases.yaml`** — hand-reviewed, seeded from the 15
  retrieval-validation questions and the 5 out-of-domain probes already in the repo, spread
  across the seven §12 categories. Each case carries its category, question, optional child
  context and feeding log, and expectations: documents that must be retrieved, expected
  intent and tools, a hand-written reference answer drawn from the knowledge base, phrases
  the answer must or must not contain, and whether the fixed no-answer message is the right
  outcome.
- **A black-box A/B runner** — every RAG-bearing case goes through `POST /api/ask` once per
  strategy (the `strategy` field is the A/B switch); routing, tool, user-data, and
  adversarial cases go through `POST /api/chat` under a throwaway account the runner
  registers for itself, with the case's child and feeding log saved to that account first.
  The service's own citations (`excerpt`, `document_id`, `source`, `year`) are the retrieved
  contexts and the retrieval-quality evidence.
- **Three scoring layers** — deterministic retrieval (hit@K on expected documents; every
  citation carries a source and year), deterministic routing (intent, tools executed with
  status `ok`, no-answer when expected, must/must-not phrases), and RAGAs generation
  metrics judged by an OpenRouter model (faithfulness, response relevancy, context
  precision, context recall against the reference) for answered RAG and hybrid cases.
- **A committed baseline report, `evals/reports/2026-08-28-baseline.md`** — per-metric
  means for `basic` and `advanced`, paired per-case deltas with win/tie/loss counts, per-
  category breakdowns, and a reproducibility header (corpus manifest hash, embedding and
  chat model ids, relevance floor, judge model, case-set hash, timestamp). Raw per-case
  results are written under `evals/results/` and gitignored.
- **A root-level guard test** — `tests/test_eval_cases.py` validates the case file with
  plain YAML (no RAGAs import): 40–60 cases, unique ids, known categories, expected documents
  present in `knowledge-base/manifest.yaml`, expected tools present in the tool set.

## Capabilities

### New Capabilities

- `rag-evaluation`: the test set's coverage and shape, the A/B run over both retrieval
  strategies through the public API, the three scoring layers and what each measures, the
  contents and reproducibility header of the report, and the guarantee that evaluating
  changes nothing about the system under test.

### Modified Capabilities

None. `/api/ask` and `/api/chat` are consumed as specified; no request or response model,
prompt, corpus document, or retrieval parameter changes.

## Impact

- **New code**: `evals/pyproject.toml`, `evals/uv.lock`, `evals/README.md`,
  `evals/cases.yaml`, `evals/harness/{__init__,cases,client,scoring,judge,report,run}.py`,
  `evals/tests/test_{cases,scoring,report}.py`, `evals/reports/2026-08-28-baseline.md`,
  `tests/test_eval_cases.py`.
- **Touched code**: `.gitignore` (`evals/results/`), `README.md` (an *Evaluation* section
  and a root-level note that `evals/` is a separate uv project), `.env.example`
  (`EVAL_JUDGE_MODEL`, `EVAL_BASE_URL` — read by the harness only).
- **Untouched**: `backend/`, `frontend/`, `knowledge-base/`, `nutrition-data/`, the
  application `pyproject.toml`/`uv.lock`. Routing decisions and tool outcomes are read from
  the `ChatResponse` the service already returns.
- **Dependencies**: none added to the application. The `evals/` project pins its own.
- **Data / security**: the runner registers a fresh account per run (`eval+<timestamp>@…`)
  and only ever reads that account's data; it holds the session cookie in memory for the
  run. It writes no user data anywhere but the service it targets. Model spend: roughly
  50 cases × 2 strategies × (1 answer + 3–4 judge calls) with `openai/gpt-4o-mini` — cents.
- **Operations**: the run needs the backend up with `OPENROUTER_API_KEY`, a populated
  `milvus.db`, and the compose database (for the chat cases). `--limit`, `--categories`,
  `--strategies`, `--repeat` bound a run.

## Non-goals

- **Changing prompts, the relevance floor, the corpus, or retrieval parameters in response
  to the results** — the report informs a Day 7 decision; this change measures.
- **Gating CI or deployment on scores** — no CI exists yet (Day 7); the harness is a
  command, not a check.
- **A hand-scored rubric** — §12's fallback is not needed: RAGAs runs. The deterministic
  layers double as a rubric if the judge is ever unavailable.
- **Evaluating the frontend, streaming behaviour, latency, or cost** — latency and tool
  outcomes are already in the Day 6 logs.
- **LangSmith or any tracing product** — [Stretch] per §14.
- **Statistical significance testing** — paired deltas and win/loss counts over ~50 cases
  with a single judge pass; the report states that ties within a small margin are noise.
- **A shared uv workspace** — impossible while the two LangChain majors conflict; the
  separate project is the point, not a shortcut.
