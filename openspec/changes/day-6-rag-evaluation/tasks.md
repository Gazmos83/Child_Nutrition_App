Additive change on `main`. Time-box: half a day plus the baseline run. Nothing under
`backend/`, `frontend/`, `knowledge-base/`, `nutrition-data/`, or the application
`pyproject.toml`/`uv.lock` changes. Authorization boundary: the harness registers its own
throwaway account per run and reads only that account's data; `/api/ask` is public.

## 1. Evaluation project

- [x] 1.1 Create `evals/pyproject.toml` (`ragas>=0.4.3,<0.5`, `langchain-openai<1`,
  `langchain-community<0.4`, `httpx`, `pyyaml`, `pydantic>=2`; dev: `pytest`, `ruff`) and
  lock it with `uv lock --project evals`; add `evals/.venv/` and `evals/results/` to
  `.gitignore`; verify `uv run --project evals python -c "from ragas.metrics.collections
  import Faithfulness; print('ok')"` prints ok and the application's `uv.lock` is unchanged
- [x] 1.2 Write `evals/README.md` (what it measures, how to run, flags, where reports go) and
  add `EVAL_JUDGE_MODEL` / `EVAL_BASE_URL` to `.env.example`; verify the README's run command
  matches `harness/run.py --help`

## 2. Test set

- [x] 2.1 Author `evals/cases.yaml`: 54 cases across the seven categories (12 rag_basic,
  10 rag_advanced, 8 tool, 6 hybrid, 6 user_data, 6 out_of_domain, 6 adversarial), seeded
  from `tests/fixtures/retrieval_validation.yaml` and the five OOD probes, each with the
  expectations its category needs and a reference answer naming the document it was drawn
  from; verify every reference is checked against its source document by the author
- [x] 2.2 Add `tests/test_eval_cases.py` to the main suite (plain YAML, no evals import):
  40–60 cases, unique ids, seven categories each ≥3, expected documents ⊆ manifest ids,
  expected tools ⊆ the tool names in `tests/test_tools_langchain.py`, seed questions present;
  verify `uv run pytest tests/test_eval_cases.py -q` passes

## 3. Harness

- [x] 3.1 `evals/harness/cases.py`: Pydantic models (`Case`, `Expect`, `ChildFixture`,
  `FeedFixture(days_ago, …)`), `load_cases(path)`, `resolve_feeds(case, now)`; verify
  `evals/tests/test_cases.py` loads the real file and rejects an unknown category and a
  duplicate id
- [x] 3.2 `evals/harness/client.py`: `ServiceClient(base_url)` with `health()`, `ask(question,
  strategy)`, `register()` (fresh `eval+<ts>@example.com`), `save_child(child)`,
  `log_feeds(child_id, feeds)`, `chat(message, child_id, strategy)`; refuses to run chat cases
  when `/health` reports the database unreachable; verify `evals/tests/test_client.py` against
  a `httpx.MockTransport` for the request shapes (`stream: false`, `strategy`, cookie reuse)
- [x] 3.3 `evals/harness/scoring.py`: deterministic layer — `retrieval_hit`, `citations_have_
  provenance`, `intent_matches`, `tools_ok`, `no_answer_correct`, `phrases_ok` → a
  `Deterministic` result per (case, strategy); verify `evals/tests/test_scoring.py` covers a
  hit, a miss, no-answer expected/unexpected, a forbidden phrase, and a tool that errored
- [x] 3.4 `evals/harness/judge.py`: build `SingleTurnSample`s from answered rag/hybrid
  results (contexts = citation excerpts in order), run the four metrics from
  `ragas.metrics.collections` with `ChatOpenAI`/`OpenAIEmbeddings` via `OPENROUTER_BASE_URL`
  and `EVAL_JUDGE_MODEL` (default `openai/gpt-4o-mini`); verify a unit test builds samples
  from a fixture result and skips no-answer cases (no network)
- [x] 3.5 `evals/harness/report.py`: reproducibility header (timestamp, case-set sha256,
  manifest sha256, embedding/chat model ids and floor from the environment, judge model,
  counts, flags used), per-strategy means, paired deltas with win/tie/loss (0.05 margin for
  judged metrics), per-category tables, failed-check list; `results.jsonl` writer; verify
  `evals/tests/test_report.py` renders a fixture into Markdown containing each section
- [x] 3.6 `evals/harness/run.py`: CLI (`--strategies`, `--categories`, `--limit`, `--repeat`,
  `--skip-judge`, `--base-url`, `--label`), streams results as cases complete, copies the
  report to `evals/reports/<date>-<label>.md`; verify `uv run --project evals ruff check
  evals && uv run --project evals pytest evals/tests -q` are green

## 4. Baseline

- [x] 4.1 With the backend up (`--no-access-log`, key and `milvus.db` present, compose DB up)
  run `uv run --project evals python -m harness.run --skip-judge` and fix any case-authoring
  errors the deterministic layer exposes; verify every out_of_domain case scores no-answer
  correct on both strategies and every retrieval case hits at least one expected document
  on `advanced`. *At apply:* the first pass exposed four authoring errors (a naive text check
  flagged foods the plan had *excluded*; "1 year" vs "12 months"; a question the router
  reasonably read as a plan request; an adversarial case whose routing to the BMI tool was
  fine) — fixed by a `plan_must_not_include` check on plan items, `a|b` phrase alternatives,
  and two reworded expectations. Three remaining failures are genuine findings kept in the
  report
- [x] 4.2 Run the full baseline `uv run --project evals python -m harness.run --label baseline`
  (both strategies, all cases, judge on) and commit `evals/reports/2026-08-28-baseline.md`;
  verify the report header is complete, each RAGAs metric has a mean per strategy and paired
  win/tie/loss counts, and the failed-check list is either empty or explained inline
- [x] 4.3 Update `README.md` with an *Evaluation (Day 6)* section (what is measured, the
  headline numbers from the baseline, how to re-run) and verify `uv run ruff check . && uv run
  pytest -q` at the root stay green and `openspec validate day-6-rag-evaluation --strict`
  passes
