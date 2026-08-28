# Evaluation harness (reference §12)

A/B comparison of the two retrieval strategies — `basic` and `advanced` — over a reviewed
54-case test set, scored three ways: deterministic retrieval and routing checks, RAGAs
generation metrics, and a per-category breakdown. It treats the running service as a black
box over HTTP and never imports `backend/`.

**Why a separate project:** RAGAs 0.4 imports LangChain 0.3 internals that no longer exist
in the LangChain 1.x line the app runs on, so the two cannot share an environment. This
directory has its own `pyproject.toml` and `uv.lock`; run everything with
`uv run --project evals …` from the repo root.

## Run

```bash
docker compose up -d                                   # chat cases need the database
uv run uvicorn backend.main:app --port 8000 --no-access-log &   # the service under test
uv run --project evals python -m harness.run --skip-judge       # deterministic pass, no spend
uv run --project evals python -m harness.run --label baseline   # full run, judge on
```

Flags: `--strategies basic,advanced` · `--categories rag_basic,tool` · `--limit N` ·
`--repeat N` (judge passes, mean reported) · `--skip-judge` · `--base-url` · `--label`.

Environment (read from the repo `.env`): `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`,
`EMBEDDING_MODEL`, `RAG_MIN_SIMILARITY` (for the report header), `EVAL_JUDGE_MODEL`
(default: the app's chat model — a known bias the report names), `EVAL_BASE_URL`.

## What is measured

- **Retrieval** — hit@K on the expected documents; every citation has a source and year.
- **Routing** — intent, tools run with status `ok`, the fixed no-answer message when and
  only when expected, must/must-not phrases (adversarial cases).
- **Generation** (answered `rag_basic`, `rag_advanced`, `hybrid` cases) — RAGAs
  faithfulness, answer relevancy, context precision, context recall against the reference,
  with the service's cited passages as the contexts.

Categories → endpoint: `rag_basic`, `rag_advanced`, `out_of_domain` → `POST /api/ask`;
`tool`, `hybrid`, `user_data`, `adversarial` → `POST /api/chat` under a throwaway account
the runner registers, with the case's child saved and feeds logged first (one child per case,
deleted afterwards).

## Output

`results/<timestamp>-<label>/results.jsonl` (raw, gitignored) and `report.md`, copied to
`reports/<date>-<label>.md` (committed). The report opens with a reproducibility header:
case-set and manifest hashes, model ids, relevance floor, judge model, and counts.

## Tests

```bash
uv run --project evals pytest evals/tests -q
uv run --project evals ruff check evals
```

The main suite's `tests/test_eval_cases.py` validates `cases.yaml` without this environment.
