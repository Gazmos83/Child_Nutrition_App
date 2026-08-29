# Child Nutrition App

A RAG + tool-calling AI assistant for child nutrition, newborn through ~4 years. It answers nutrition questions from a curated pediatric-guideline corpus and generates nutrient-specific meal plans from a stored child profile: age in months, weight, gender, allergies, diet preference, and any doctor's note.

> **Not a medical device.** Every recommendation ships with a disclaimer that this is not medical advice and that a pediatrician should be consulted.

> **Status:** Day 7 of 7 — production hardening and deployment in progress. PostgreSQL schema and migrations, the curated knowledge base with its ingestion pipeline, the basic/advanced RAG pipeline behind `POST /api/ask`, the deterministic nutrient tools (targets, food lookup, infant-safety filter, doctor's-note override, meal-plan generation), the intent router behind `POST /api/chat`, the Next.js chat UI, the feeding log with nutrient-gap detection (reference §9b), and accounts with saved child profiles and a persisted feeding log are implemented. Deployment follows on Day 7. See [`CLAUDE.md`](./CLAUDE.md) for the settled architecture and rules.

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

Every user-scoped read and write is bound to the authenticated user's identity — one user must never reach another's child profiles or feeding log. Sign-in is email + password (argon2id hashes, `argon2-cffi`); the session is a signed token (HS256, PyJWT, `SESSION_SECRET`) in an `HttpOnly`, `SameSite=Lax` cookie, so the browser never handles a token and a cross-site form post carries neither the cookie nor an acceptable content type. `backend/api/deps.py` holds the two dependencies every user-scoped route runs behind: `get_current_user` (401 without a valid session; a deactivated or deleted account is refused on its next request) and `owned_child` (the single place the ownership predicate is written; a non-owner gets the same 404 as a nonexistent id, so probes learn nothing). `tests/test_api_children.py` is the evidence: owner-only listing, byte-identical 404s for non-owner and nonexistent, and a loop over the OpenAPI schema asserting every user-scoped operation returns 401 without a cookie.

`POST /api/chat` no longer accepts the child's details or the feeding log in the body: it takes a `child_id` (optional when the account has one child) and reads both from the account's own rows, so the stored profile is the only authority for the numbers a plan is built from. `POST /api/ask` requires a session too (Day 7) — not because it reads user data (it doesn't; it persists nothing and uses the identity for admission only) but because every answer spends model credit; the evaluation harness registers an account before its first request. `GET /api/foods` and the register/login routes stay public.

All API inputs, tool inputs, and LLM-generated tool arguments are validated with Pydantic before use. The LLM never executes arbitrary SQL; all data access goes through validated, auth-scoped application code.

**Abuse ceilings (Day 7).** The model-spending routes (`/api/ask` and `/api/chat`, one shared budget) and the credential routes (register, login) are rate-limited per client address — `RATE_LIMIT_MODEL_PER_MINUTE` (default 30) and `RATE_LIMIT_AUTH_PER_MINUTE` (default 10); `0` disables — answering 429 with a `Retry-After` header before any retrieval, model call, or password work (`backend/api/rate_limit.py`, a route dependency). The limiter is in-process, which is exact because the service runs as one instance; behind the hosting proxy the client address comes from `X-Forwarded-For` through uvicorn's `--proxy-headers`, which only the container start script passes. Cross-origin browser access is an explicit allowlist, `ALLOWED_ORIGINS` (comma-separated, default empty, never `*`): the browser reaches the API through the Next.js same-origin rewrite, so nothing is granted unless configured. With `APP_ENV=prod` the application refuses to start without `SESSION_SECRET` and `OPENROUTER_API_KEY` rather than serving 503s.

**Never logged:** passwords, password hashes, session tokens, cookies, request headers, email addresses, the client address, and the text of the parent's message or the assistant's answer (only the message length). Records carry identifiers — `user_id`, `child_profile_id` — never emails. The doctor's note stays in the meal-plan and gap-detection audit snapshots because hard rule 8 requires it; `AUDIT_LOG_PATH` lets those records be kept in their own file. `tests/test_api_auth.py::TestNothingSensitiveIsLogged` registers and signs in with every logger at `DEBUG` and asserts none of that material appears.

Meal-plan recommendations are logged with a full input snapshot (age, weight, gender, allergies, diet preference, doctor's note, rule/source used) for auditability.

## Development

Python dependencies are managed with [uv](https://docs.astral.sh/uv/) (Python 3.14 pinned, `uv.lock` committed and authoritative); frontend dependencies with pnpm.

```bash
uv sync                  # create/refresh .venv from uv.lock
uv add <package>         # add a dependency
uv add --dev <package>   # add a dev-only dependency
docker compose up -d     # PostgreSQL 17 on 127.0.0.1:5432 (dev + test databases)
uv run alembic upgrade head   # apply the schema (DATABASE_URL from .env)
uv run pytest            # offline tests + the PostgreSQL-backed `db` tests
uv run pytest -m integration  # live OpenRouter/Milvus tests; spends credit
uv run ruff check .      # lint

pnpm install             # frontend deps (pnpm workspace; `frontend/` is the only package)
pnpm -C frontend dev     # Next.js dev server on :3000, proxying /api/* to the backend
pnpm -C frontend lint && pnpm -C frontend typecheck && pnpm -C frontend test
```

`docker-compose.yml` runs the database only; the backend (`uv run uvicorn backend.main:app --reload`) and the frontend stay on the host. `docker compose down -v` resets it. Migrations live in `alembic/versions/` and are hand-written: the initial one creates the five PostgreSQL enum types before the tables and its `downgrade()` drops them after, so `uv run alembic downgrade base && uv run alembic upgrade head` round-trips — `tests/test_migrations.py` checks exactly that. Tests marked `db` bind to `TEST_DATABASE_URL` (a separate database the compose file creates, so the fixtures can never touch development data); when it is unset they skip, when it is set but unreachable they fail.

Always add dependencies through the package manager (`uv add`, `pnpm add`) and run Python via `uv run`. Never `pip install` into `.venv`, and never hand-edit a lockfile.

### Configuration

Copy `.env.example` to `.env`. `DATABASE_URL` points at PostgreSQL (the app boots and reports `degraded` on `/health` without it); `TEST_DATABASE_URL` is the database the test suite may create and drop; `SESSION_SECRET` (32+ characters) signs session cookies — without it every authenticated route returns 503 naming it. `LOG_FORMAT` (`json`, the default, or `text`), `LOG_LEVEL` (default `INFO`), and `AUDIT_LOG_PATH` (optional file for the hard-rule-8 audit records) configure logging — see *Logging and monitoring* below. Run uvicorn with `--no-access-log`: the application writes its own access record per request. `OPENROUTER_API_KEY` is needed to embed the corpus and to answer questions — both the chat model and the embedding model are served by OpenRouter (`OPENROUTER_MODEL`, `EMBEDDING_MODEL`). Without the key the app still boots; `POST /api/ask` and `POST /api/chat` return 503 naming the missing setting. `APP_ENV=prod` changes that: the session cookie becomes `Secure`, and a missing `SESSION_SECRET` or `OPENROUTER_API_KEY` stops the process at start with the setting's name. `ALLOWED_ORIGINS`, `RATE_LIMIT_MODEL_PER_MINUTE`, and `RATE_LIMIT_AUTH_PER_MINUTE` are described under *Security*. The frontend reads one server-side variable, `BACKEND_URL` (default `http://localhost:8000`, see `frontend/.env.example`), used by Next.js rewrites so the browser only ever talks to the Next.js origin.

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

The endpoint requires a session (Day 7), so sign in once into a cookie jar:

```bash
curl -s -c jar localhost:8000/api/auth/register -H 'content-type: application/json' \
  -d '{"email": "parent@example.com", "password": "correct horse battery"}'
```

JSON (used by tests and evaluation):

```bash
curl -s -b jar localhost:8000/api/ask -H 'content-type: application/json' \
  -d '{"question": "How much iron does a 9-month-old need?", "strategy": "advanced", "stream": false}'
```

Server-sent events (used by the UI): `token` events carry answer fragments, one `citations` event carries citations + retrieval metadata + disclaimer, then `done` (or `error`).

```bash
curl -N -b jar localhost:8000/api/ask -H 'content-type: application/json' \
  -d '{"question": "When can babies have honey?"}'
```

`strategy` is `basic` (single query, top-K) or `advanced` (age extraction → metadata filter → query translation → multi-query fusion → dedup; the default). Both share the same prompt, so Day 6's A/B evaluation compares retrieval alone. Every response carries citations with source and year and a fixed not-medical-advice disclaimer; when nothing in the knowledge base is relevant, the endpoint returns a fixed explanation instead of calling the model.

Note that LangChain resolves to 1.x and `pymilvus` to 3.x — both past major-version breaks from the 0.x/2.x APIs most tutorials still use. Check the current docs rather than pattern-matching from older examples.

## Deterministic tools (Day 4)

Ten tools in `backend/tools/`, each taking a Pydantic-validated input and never asking the
model for a number. `backend/tools/langchain_tools.py::build_tools(chat_model)` exposes
them as LangChain `StructuredTool`s, which the Day 5 router binds (see below).

| Tool | What it does | Source of the numbers |
|---|---|---|
| `calculate_bmi` | weight / height² | CDC definition |
| `calculate_calorie_target` | Estimated Energy Requirement by age band; height + activity from 36 months | 2005 DRI EER equations |
| `calculate_protein_target` | g/kg by age band | DRI AI/RDA |
| `lookup_food` | one row of the food table: nutrients, allergens, safety flags, minimum age, source | `nutrition-data/foods.yaml` |
| `calculate_meal_nutrition` | sums foods × servings; unknown ids reported, never dropped | `nutrition-data/foods.yaml` |
| `generate_meal_plan` | targets → doctor's-note override → diet filter → infant-safety filter → composition → safety re-check → totals + disclaimer + audit log; optionally steered by a gap report and today's logged feeds (below) | all of the above |
| `log_feeding` | validates one feed (type from a closed vocabulary, table food, quantity, unit), prices it from the table, assigns an id; stores nothing until Day 6 | `nutrition-data/foods.yaml` |
| `get_daily_nutrition` | one local day's totals from the feeding log | `nutrition-data/foods.yaml` |
| `get_remaining_targets` | the day's targets (doctor's note honoured) minus intake, floored at zero | DRI + food table |
| `detect_nutrient_gaps` | rolling-window intake vs. targets with confidence that grows with complete days logged | DRI + food table |

`nutrition-data/foods.yaml` is a hand-curated, validated table (~55 infant/toddler foods,
USDA FoodData Central figures per serving) carrying the "big nine" allergens and the
choking-hazard / honey / unpasteurised flags the safety filter reads. The whole file is
rejected if any entry is invalid. The safety filter (`backend/nutrition/safety.py`) has no
switch that disables a rule and runs on both the candidates and the finished plan.

A doctor's note is extracted by the chat model into a bounded structure (nutrient ∈
calories/protein/iron, direction, value, unit) and applied by plain Python: on conflict the
note wins and the conflict is an explicit field; if extraction fails, the plan is still
generated and the note is flagged as not applied. Every `generate_meal_plan` call emits one
JSON line on the `backend.tools.audit` logger with the full input snapshot.

```bash
uv run pytest tests/test_nutrition_*.py tests/test_tools_*.py tests/test_schemas_tools.py
```

## Chat, routing, and the UI (Day 5)

`POST /api/chat` is the routed assistant. One model call with the six tools plus a
`search_guidelines` pseudo-tool bound decides the path — the model's tool calls *are* the
routing decision — and plain Python executes it: `rag` (knowledge base only, delegating to
the Day 3 pipeline unchanged), `tool` (deterministic tools only), or `hybrid` (both). The
model's own free text is never returned; every answer is composed from retrieved context
blocks and/or validated tool results. At most four tool calls per message, one round, no
agent loop.

The child's details (age in **months**, weight, sex, optional height, diet preference,
allergies from the controlled vocabulary, doctor's note, activity level) come from the side
panel in the UI and travel in the request body. They are **authoritative**: any
profile-backed argument the model proposes is replaced by the request's value and the tool
activity says so (`used_context`). Nothing is persisted and no identity is taken — Day 6
swaps this seam for auth-scoped profiles.

```bash
curl -N localhost:8000/api/chat -H 'content-type: application/json' -d '{
  "message": "How much protein does my child need?",
  "child": {"age_months": 8, "weight_kg": 8.5, "sex": "female", "allergies": ["peanut"],
            "diet_preference": "omnivore", "activity_level": "low_active"},
  "history": []
}'
```

Server-sent events, in order: one `route` (intent + planned capabilities), one `tool` per
invocation (name, status, validated args, `used_context`, result or a parent-facing
error), `token`s, one `final` (citations with source + year, retrieval statistics,
disclaimer, tool summary), then `done` — or a terminal `error`. `"stream": false` returns
the same content as JSON (`answer, intent, tools, citations, retrieval, disclaimer`). A
failed tool (unknown food, missing height, …) becomes an error entry and the answer still
completes. Every routing decision is logged on `backend.chat.router` with intent, tools,
retrieval statistics, and latency.

The UI (`frontend/`, Next.js App Router + Tailwind + shadcn/ui + TanStack Query) is one
screen: the child-details panel and the chat. Each assistant message shows the intent, one
chip per tool (expandable to arguments and result), a structured meal-plan card when
`generate_meal_plan` ran — with an unmissable banner when the doctor's note overrode a
target — the answer with `[n]` citation markers, a numbered Sources list with publication
year, and the not-medical-advice disclaimer. All parent-facing copy lives in
`frontend/src/lib/copy.ts` and `backend/chat/copy.py` (warm by default; direct about
safety and errors).

```bash
uv run pytest tests/test_chat_*.py tests/test_api_chat.py tests/test_schemas_chat.py
pnpm -C frontend test
```

## Feeding log and nutrient gaps (Day 5, second change)

Everything above produces *targets*. The feeding log captures what the child actually had
(reference §9b): each entry is a time-zone-aware timestamp, a feeding type from the closed
vocabulary `breastmilk | formula | solid | water`, a food from the table for solids, a
quantity and unit. Breast milk may be logged without a quantity — direct breastfeeding has
no measure — and such an entry contributes no nutrients and marks its day *incomplete*. An
entry's nutrients are `quantity ÷ serving size × per-serving` from `foods.yaml`; the model
never computes them, and the backend never trusts client-supplied figures.

**The log is client-held until Day 6.** The Feeding-log tab in the side panel posts each
feed to `POST /api/feedings` (validate, price, assign an id; nothing stored), keeps the
result in the browser for fourteen days, and sends the entries with every `/api/chat`
request together with the browser's IANA `timezone`. `GET /api/foods` lists the table for
the picker. Log-backed tool arguments (`entries`, `logged_today`, `timezone`) are always
filled from the request, never from the model. Day 6 adds the `feeding_log` table and the
auth-scoped read/write behind the same handler.

`detect_nutrient_gaps` compares logged intake with the child's targets — the same
note-overridden targets the planner uses, so a prescribed calorie limit is never reported
as a deficit — over a window that widens with *complete* days (at least one entry, no
unmeasured feed) in the last fourteen days, excluding the reference day itself: 0 days →
`insufficient_data`; 1–2 → `low` confidence, directional only; 3–6 → `medium`, three-day
window; 7+ → `high`, seven-day window. Per nutrient (calories, protein, iron) the report
gives the average, target, ratio, and a flag (`below` < 0.80, `above` > 1.20, else
`adequate`), with the target's source and age band.

`generate_meal_plan` accepts the report and today's entries. A `below` flag at `medium` or
`high` confidence makes the composer favour foods dense in that nutrient — targets are
never raised and the iron upper limit stays in force; a `low` flag changes nothing. Today's
intake is subtracted so the plan covers the rest of the day (`already_logged` is reported),
and when under ten percent of the calorie target remains the outcome is `targets_met`. With
no report and no entries the plan is byte-identical to the Day 4 planner (regression-tested
against `tests/fixtures/meal_plans_before_change_2.json`). When a plan is requested and
the request carries a log, the chat service runs gap detection first and hands the report
to the planner. The audit line gains the gap report, the logged entries, and the
adjustments; gap detection emits its own `nutrient_gaps_audit` line.

```bash
uv run pytest tests/test_nutrition_feeding.py tests/test_nutrition_gaps.py \
  tests/test_tools_feeding_log.py tests/test_tools_nutrient_gaps.py tests/test_api_feedings.py
```

## Evaluation (Day 6)

`evals/` is a **separate uv project** (RAGAs 0.4 needs LangChain 0.3, the app runs 1.x) that
evaluates the running service as a black box over HTTP — see [`evals/README.md`](./evals/README.md).
It runs a reviewed 54-case test set (`evals/cases.yaml`; seven categories: basic and advanced
knowledge-base questions, tool, hybrid, user-data, out-of-domain, adversarial) through both
retrieval strategies and scores three ways: deterministic retrieval/routing/safety checks,
RAGAs generation metrics (faithfulness, answer relevancy, context precision, context recall),
and a per-category breakdown. `tests/test_eval_cases.py` in the main suite keeps the case file
valid without the evals environment.

```bash
uv run --project evals python -m harness.run --skip-judge        # deterministic layers only, no spend
uv run --project evals python -m harness.run --label baseline    # full A/B with the RAGAs judge
```

**Baseline (2026-08-28, [`evals/reports/2026-08-28-baseline.md`](./evals/reports/2026-08-28-baseline.md)):**
`basic` and `advanced` tie on every deterministic check — 100% retrieval hit and citation
provenance, 100% correct no-answer on out-of-domain and adversarial probes — and sit within noise
on generation (faithfulness 0.853 vs 0.867, context precision 0.919 vs 0.891, context recall
0.943 vs 0.923; 28 judged cases each), with `advanced` ~1.3 s slower at the median. Three
findings, not test-set errors: the vegan-diet answer omits B12, "what's in X plus Y" never
reaches `calculate_meal_nutrition`, and one food-table question routed to the knowledge base
in one of four runs. Prompts and corpus were frozen for this baseline; acting on the findings is
a Day 7 decision.

## Logging and monitoring (Day 6)

Structured logs are the MVP observability deliverable (reference §14); no dashboard. Every record is one line — a JSON object by default (`LOG_FORMAT=json`), or readable text — and every record emitted while handling a request carries the same three correlation fields: `request_id`, `user_id` (from the session), and `child_profile_id` (from the account's stored profile the request resolved). Nothing in `backend/tools/` or `backend/nutrition/` knows about any of this: the values live in `contextvars` set by the middleware and the auth dependencies, and a logging filter stamps them onto each record.

Record types, by logger:

| Logger | One record per | Fields |
|---|---|---|
| `backend.api.access` | request (at `DEBUG` for `/health`) | `method`, `route` (template, e.g. `/api/children/{child_id}`), `status`, `latency_ms`, `user_id` |
| `backend.chat.router` | chat message | intent, planned/executed capabilities with outcomes, retrieval stats, `message_chars`, `latency_ms` |
| `backend.chat.tools` | tool invocation | `tool`, `status`, `latency_ms`, `used_context` (which args came from the profile/log), `error_kind` |
| `backend.rag.pipeline` | knowledge-base retrieval | `strategy`, `queries`, `retrieved`, `kept`, `top_score`, `latency_ms` |
| `backend.tools.audit` | meal plan / gap detection (hard rule 8) | the full input snapshot as JSON in the message; correlation fields on the record |
| `backend.api.errors` | unhandled exception | traceback; the client gets `500 {"detail", "request_id"}` and never a traceback |

Every response carries `X-Request-ID` (a well-formed incoming one is honoured, so a proxy's id threads through); a streamed `error` event on `/api/chat` or `/api/ask` carries `request_id` too. To follow one request end to end:

```bash
uv run uvicorn backend.main:app --port 8000 --no-access-log > app.log
curl -si localhost:8000/api/foods | grep -i x-request-id
grep '"request_id": "<the id>"' app.log
```

Set `AUDIT_LOG_PATH=audit.jsonl` to write the audit records to their own file (and not to the main log) when they need longer retention than the rest.

## Project docs

- [`CLAUDE.md`](./CLAUDE.md) — working context for AI coding assistants: stack, architecture principle, hard rules, scope discipline.
- `Nutrition_App_Full_Reference.md` — the long-form spec: full rationale, RAG strategy, evaluation design, and production migration path.
