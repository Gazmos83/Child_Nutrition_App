# Child Nutrition App

A RAG + tool-calling AI assistant for child nutrition, newborn through ~4 years. It answers nutrition questions from a curated pediatric-guideline corpus and generates nutrient-specific meal plans from a stored child profile: age in months, weight, gender, allergies, diet preference, and any doctor's note.

> **Not a medical device.** Every recommendation ships with a disclaimer that this is not medical advice and that a pediatrician should be consulted.

> **Status:** early development (Day 3 of 7). PostgreSQL schema, the curated knowledge base with its ingestion pipeline, and the basic/advanced RAG pipeline behind `POST /api/ask` are implemented. Deterministic tools, routing, auth, and the UI follow on Days 4–7. See [`CLAUDE.md`](./CLAUDE.md) for the settled architecture and rules.

## Features

- **Nutrient-specific meal plans** — built from the child's stored profile. All quantities come from lookup-table-driven Python code; the LLM extracts structured inputs but never generates nutrient numbers itself.
- **Grounded nutrition answers** — retrieval over a curated corpus drawn from recognized pediatric guidelines (WHO Child Growth Standards, AAP, national infant dietary guidelines). Every RAG-backed answer cites its source and publication date.
- **Deterministic nutrition tools** — BMI, calorie and protein targets, food lookup, per-meal nutrition, daily totals, and remaining targets. Typed inputs, Pydantic-validated, authorization-checked, with structured results and graceful failure handling.
- **Hard-coded infant-safety filter** — every meal plan passes safety checks that run independently of the RAG/LLM pipeline and cannot be bypassed or overridden by the model: no honey under 12 months, no choking hazards, no unpasteurized products.
- **Doctor's-note precedence** — when a clinician's note conflicts with general nutrient targets, the note wins. The conflict is surfaced in the UI rather than silently blended away.
- **Intent routing** — a lightweight classifier picks the execution path per query, then runs it deterministically.
- **Meal logging and daily tracking** — log meals and meal items, then read back nutrition summaries and what's still outstanding against the day's targets.
- **Transparent responses** — streamed answers carrying citations, tool-activity indicators, and conversation history, so it's visible which sources and which tools produced a given reply.
- **Re-runnable knowledge ingestion** — an idempotent job re-embeds new or changed documents and upserts them into the vector store without a full rebuild.

## How it works

The governing principle is **deterministic code → RAG → tools → lightweight routing**, not agent-everywhere. AI is used where it adds genuine value; anything computable is computed in plain Python.

A router classifies each query and dispatches:

```
"What is fiber?"                            → RAG
"What's my child's BMI?"                    → Tool
"How much protein does my toddler need?"    → Tool + child profile
"What should my 8-month-old eat this week?"  → RAG + tools + user data
```

Retrieval runs in two stages: a basic path (embed → vector search → top-K → prompt), and an advanced path adding query analysis and translation, multi-query retrieval, metadata filtering, deduplication, and context construction.

Response shape:

```
User: How much protein does my child still need today?
AI:   You have approximately 42g remaining today.
      Sources: • Nutrition guideline
      Tools used: ✓ Daily nutrition ✓ Protein target calculator
```

## Stack

| Layer | Tech |
|---|---|
| Frontend | Next.js, React, TypeScript, Tailwind, shadcn/ui, TanStack Query |
| Backend | Python, FastAPI, Pydantic, SQLAlchemy, Alembic |
| LLM | LangChain via OpenRouter (OpenAI-compatible SDK) |
| Vector DB | Milvus Lite, behind a vector-store abstraction |
| App DB | PostgreSQL |
| Tooling | uv (Python), pnpm (frontend) |

FastAPI owns REST, auth boundaries, streaming, and validation; AI logic stays separate from HTTP concerns. The vector store sits behind an abstraction so moving from Milvus Lite to Standalone/Zilliz doesn't touch business logic.

## Data model constraints

Three constraints are load-bearing and worth knowing before touching the schema:

- **Age is stored and reasoned about in months**, not years — nutrient requirements shift fast in the first year.
- **Allergies and diet preference are enum/controlled-vocabulary fields**, never free text.
- **PostgreSQL is the authoritative app store** for users, child profiles, meals, daily nutrition, and conversations. Milvus holds knowledge-base vectors only, never primary application data.

## Security

Every user-scoped read and write is bound to the authenticated user's identity — one user must never reach another's child profiles, meals, or conversations. All API inputs, tool inputs, and LLM-generated tool arguments are validated with Pydantic before use. The LLM never executes arbitrary SQL; all data access goes through validated, auth-scoped application code.

Meal-plan recommendations are logged with a full input snapshot (age, weight, gender, allergies, diet preference, doctor's note, rule/source used) for auditability.

## Development

Python dependencies are managed with [uv](https://docs.astral.sh/uv/) (Python 3.14 pinned, `uv.lock` committed and authoritative); frontend dependencies with pnpm.

```bash
uv sync                  # create/refresh .venv from uv.lock
uv add <package>         # add a dependency
uv add --dev <package>   # add a dev-only dependency
uv run pytest            # unit tests (offline); add -m integration for live tests
uv run ruff check .      # lint
```

Always add dependencies through the package manager (`uv add`, `pnpm add`) and run Python via `uv run`. Never `pip install` into `.venv`, and never hand-edit a lockfile.

### Configuration

Copy `.env.example` to `.env`. `DATABASE_URL` points at PostgreSQL (the app boots and reports `degraded` on `/health` without it). `OPENROUTER_API_KEY` is needed to embed the corpus and to answer questions — both the chat model and the embedding model are served by OpenRouter (`OPENROUTER_MODEL`, `EMBEDDING_MODEL`). Without the key the app still boots; `POST /api/ask` returns 503 naming the missing setting.

### Knowledge base

The corpus lives in `knowledge-base/` as hand-condensed Markdown summaries of recognized pediatric guidelines (WHO, AAP, CDC, USDA/HHS, NIH, FDA/EPA). `knowledge-base/manifest.yaml` carries each document's citation metadata — source title, publication year, topic, authority, and the age range in months it applies to.

```bash
uv run scripts/ingest.py     # embed new/changed documents into milvus.db (idempotent)
```

Ingestion is incremental: it hashes every document, compares against what `milvus.db` already holds, and re-embeds only new or changed files, replacing each document's chunks as a unit. Re-running with no changes embeds nothing.

**To add a source:** drop a `.md` file in `knowledge-base/` (use `## Section` headings — chunks record the nearest heading for citations), add a manifest entry (`file, source, year, topic, authority, age_min_months, age_max_months, url`), and re-run `uv run scripts/ingest.py`. Changing `EMBEDDING_MODEL` requires deleting `milvus.db` and re-ingesting; the store refuses to search a collection built with a different model.

### Asking a question

```bash
uv run uvicorn backend.main:app --reload
```

JSON (used by tests and evaluation):

```bash
curl -s localhost:8000/api/ask -H 'content-type: application/json' \
  -d '{"question": "How much iron does a 9-month-old need?", "strategy": "advanced", "stream": false}'
```

Server-sent events (used by the UI): `token` events carry answer fragments, one `citations` event carries citations + retrieval metadata + disclaimer, then `done` (or `error`).

```bash
curl -N localhost:8000/api/ask -H 'content-type: application/json' \
  -d '{"question": "When can babies have honey?"}'
```

`strategy` is `basic` (single query, top-K) or `advanced` (age extraction → metadata filter → query translation → multi-query fusion → dedup; the default). Both share the same prompt, so Day 6's A/B evaluation compares retrieval alone. Every response carries citations with source and year and a fixed not-medical-advice disclaimer; when nothing in the knowledge base is relevant, the endpoint returns a fixed explanation instead of calling the model.

Note that LangChain resolves to 1.x and `pymilvus` to 3.x — both past major-version breaks from the 0.x/2.x APIs most tutorials still use. Check the current docs rather than pattern-matching from older examples.

## Project docs

- [`CLAUDE.md`](./CLAUDE.md) — working context for AI coding assistants: stack, architecture principle, hard rules, scope discipline.
- `Nutrition_App_Full_Reference.md` — the long-form spec: full rationale, RAG strategy, evaluation design, and production migration path.
