# Little Gourmant

A child-nutrition assistant for newborns through roughly four years old. Parents ask
questions in plain language and get answers grounded in recognised pediatric guidelines,
plus nutrient-specific meal plans built from their own child's profile — date of birth,
weight, height, sex, allergies, diet preference, and any doctor's-note or household
preference rows.

> **Not a medical device.** Every answer and every plan ships with a disclaimer that this
> is not medical advice and that a pediatrician should be consulted.

---

## What it does

| Capability | What the parent gets |
|---|---|
| **Grounded answers** | Retrieval over a curated corpus of pediatric guidelines. Every answer cites its source and publication year; when nothing relevant is found the assistant says so instead of guessing. |
| **Nutrient-specific meal plans** | Plans composed from the child's stored profile against age-appropriate targets, with the doctor's note honoured and every item safety-checked. |
| **Daily targets** | Reference targets for the child's exact age in months, annotated with how the last two weeks of logged intake compare. |
| **Feeding log** | Log breast milk, formula, solids and water. Nutrients are priced from the internal food table, never from the model. |
| **Nutrient-gap detection** | A rolling-window comparison of intake against targets, with a confidence level that grows as more complete days are logged. |
| **Growth tracking** | Weight and height measurements plotted against WHO Child Growth Standards percentile curves, with z-scores and percentiles across four indicators. |
| **Transparent responses** | Each reply shows the routing decision, one expandable chip per tool that ran, numbered citations, and the disclaimer. |

### Who it is for

Parents and caregivers of children under about four who want a concrete answer — "how
much iron does a nine-month-old need?", "what should she eat for the rest of today?" —
rather than a search-results page. The product deliberately refuses to be a diagnostic
tool: it computes against published reference values and defers to the child's doctor
wherever the two disagree.

---

## How it works

The governing principle is **deterministic code → retrieval → tools → lightweight
routing**. The model is used where language understanding genuinely helps; anything
computable is computed in plain Python.

```
                    ┌──────────────┐
   parent message → │    router    │  one model call, tools bound
                    └──────┬───────┘
             ┌─────────────┼─────────────┐
             ▼             ▼             ▼
           rag            tool         hybrid
        retrieval    deterministic     both
             │         functions         │
             └─────────────┼─────────────┘
                           ▼
                 composed answer + citations
                 + tool activity + disclaimer
```

The model's tool calls *are* the routing decision; plain Python then executes them. The
model's own free text is never returned to the parent — every answer is composed from
retrieved context blocks and validated tool results.

```
"What is fiber?"                           → rag
"What's my child's BMI?"                   → tool
"How much protein does my toddler need?"   → tool + stored profile
"What should my 8-month-old eat today?"    → hybrid
```

**The LLM never produces a nutrient number.** It extracts structured inputs and picks a
path; every quantity comes from a lookup table or a reference equation in Python.

Retrieval runs one of two strategies. `basic` embeds the question, searches, and keeps
the top matches. `advanced` (the default) adds age extraction, metadata filtering, query
translation, multi-query fusion and deduplication. Both share the same answer prompt, so
they can be compared on retrieval quality alone.

---

## Safety and compliance

These rules are structural, not advisory. They are enforced in code that the model
cannot reach or override.

1. **Age is stored and reasoned about in months.** The profile holds a birth date; every
   age the API returns is a whole number of completed months, derived on read.
   Requirements shift too fast in the first year for years to be a useful unit.
2. **Allergies and diet preference are controlled vocabularies**, never free text.
3. **The doctor's note wins.** Notes are rows, each either a doctor's instruction or a
   household preference. When a doctor's row conflicts with a general target, the row
   applies and the conflict is surfaced explicitly — never silently blended. A preference
   row can only exclude foods; it can never move a target.
4. **A hard-coded infant-safety filter** runs on every plan, independently of the
   retrieval and model path, with no switch that disables a rule: no honey under twelve
   months, no choking hazards, no unpasteurised products. It runs on the candidate foods
   and again on the finished plan.
5. **Citations are mandatory** on knowledge-backed answers — source title and publication
   year, drawn from recognised guidelines (WHO, AAP, CDC, USDA/HHS, NIH, FDA/EPA).
6. **No model-executed SQL.** All data access goes through validated, auth-scoped
   application code.
7. **Every input is validated with Pydantic** — API bodies, tool inputs, and the
   arguments the model proposes for a tool.
8. **Every meal plan is logged with its full input snapshot** — age, weight, sex,
   allergies, diet preference, the note rows and what each one did, and the food-table
   revision used — for auditability.
9. **Every user-scoped read and write is bound to the authenticated account.** One user
   can never reach another's child profiles, feeding log or growth log.
10. **Live external nutrition data is exception-only and gated.** See
    [External food lookup](#external-food-lookup).

---

## Stack

| Layer | Tech |
|---|---|
| Frontend | Next.js 16 (App Router), React 19, TypeScript, Tailwind 4, shadcn/ui, TanStack Query |
| Backend | Python 3.14, FastAPI, Pydantic, SQLAlchemy (async), Alembic |
| Model access | LangChain via OpenRouter — one provider for both the chat and embedding models |
| Vector store | Milvus Lite, behind an abstraction so the store can be swapped without touching business logic |
| Application database | PostgreSQL — accounts, child profiles, feedings, growth measurements, food-table revisions |
| Tooling | uv (Python, `uv.lock` authoritative), pnpm (frontend), Docker Compose (local PostgreSQL only) |

PostgreSQL is the authoritative application store. Milvus holds knowledge-base vectors
only — never primary application data. Growth charts are hand-rolled inline SVG; there is
no charting dependency.

---

## Repository layout

```
backend/          FastAPI application
  api/            routes, dependencies, rate limiting, SSE
  auth/           password hashing, session tokens
  chat/           router, service, response composition, copy
  core/           settings
  db/ models/     SQLAlchemy session and ORM models
  knowledge/      corpus loading and chunking
  nutrition/      pure-Python domain logic (targets, safety, growth, gaps, foods)
  rag/            retrieval pipeline and vector-store abstraction
  schemas/        Pydantic request/response and tool models
  tools/          the deterministic tools exposed to the router
frontend/         Next.js application (src/app, src/components, src/lib, src/hooks)
knowledge-base/   curated Markdown corpus + manifest.yaml citation metadata
nutrition-data/   foods.yaml, who-growth-standards.yaml
alembic/          database migrations
evals/            standalone RAGAs evaluation harness (its own uv project)
scripts/          ingest.py, build_growth_tables.py, start.sh
tests/            backend test suite
Dockerfile        API image
render.yaml       Render blueprint: API service + managed PostgreSQL
```

---

## Getting started

**Prerequisites:** [uv](https://docs.astral.sh/uv/), [pnpm](https://pnpm.io/), Docker
(for local PostgreSQL), and an [OpenRouter](https://openrouter.ai/keys) API key.

```bash
git clone <repo> && cd Baby_Nutrient_App
cp .env.example .env          # then fill in SESSION_SECRET and OPENROUTER_API_KEY

uv sync                       # Python deps from uv.lock
pnpm install                  # frontend deps

docker compose up -d          # PostgreSQL 17 on 127.0.0.1:5432 (dev + test databases)
uv run alembic upgrade head   # apply the schema
uv run scripts/ingest.py      # embed the corpus into milvus.db
```

Run the two processes in separate terminals:

```bash
uv run uvicorn backend.main:app --reload --no-access-log   # API on :8000
pnpm -C frontend dev                                       # UI on :3000
```

Open <http://localhost:3000>, register an account, and fill in the child profile in the
**Child** tab. `docker compose down -v` resets the database.

The API writes its own structured access record per request, so run uvicorn with
`--no-access-log` to avoid a duplicate line.

Always add dependencies through the package manager (`uv add`, `uv add --dev`,
`pnpm add`) and run Python through `uv run`. Never `pip install` into `.venv`, and never
hand-edit a lockfile.

### Configuration

Everything is read from the environment; `.env.example` documents each setting inline.

| Setting | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL connection. A bare `postgresql://` URL is normalised to the asyncpg driver automatically. |
| `TEST_DATABASE_URL` | Separate database the test suite may create and drop. Deliberately not derived from `DATABASE_URL`. |
| `APP_ENV` | `dev` \| `test` \| `prod`. Outside `dev` the session cookie is `Secure`-only; in `prod` the app refuses to start without `SESSION_SECRET` and `OPENROUTER_API_KEY`. |
| `SESSION_SECRET` | Signs session cookies, 32+ characters. Rotating it signs everyone out. |
| `SESSION_TTL_HOURS` | How long a sign-in lasts. Default 168 (seven days). |
| `OPENROUTER_API_KEY` | Required to embed the corpus and to answer questions. |
| `OPENROUTER_MODEL` / `EMBEDDING_MODEL` | Chat and embedding model ids. |
| `MILVUS_DB_PATH` / `CORPUS_DIR` | Vector-store file and corpus directory. |
| `RAG_MIN_SIMILARITY` | Cosine floor below which passages are discarded. Default `0.45`. |
| `RAG_CONTEXT_CHAR_BUDGET` | Maximum characters of retrieved context in the answer prompt. |
| `ADMIN_EMAILS` | Comma-separated accounts allowed to edit the food table. Empty grants nobody the role; there is no route that grants it. |
| `ALLOWED_ORIGINS` | Credentialed cross-origin allowlist, comma-separated. Never `*`, empty by default. |
| `RATE_LIMIT_MODEL_PER_MINUTE`, `RATE_LIMIT_AUTH_PER_MINUTE`, `RATE_LIMIT_ADMIN_PER_MINUTE` | Per-client request ceilings. Defaults 30 / 10 / 30; `0` disables. |
| `LOG_FORMAT` / `LOG_LEVEL` / `AUDIT_LOG_PATH` | See [Logging](#logging-and-monitoring). |
| `EXTERNAL_FOOD_*`, `USDA_FDC_API_KEY` | See [External food lookup](#external-food-lookup). Off by default. |
| `BACKEND_URL` | Frontend-side only. Where Next.js rewrites `/api/*`. Default `http://localhost:8000`. |

Missing configuration degrades rather than crashes in development: without
`DATABASE_URL` the app boots and reports `degraded` on `/health`, and without
`OPENROUTER_API_KEY` the model routes return `503` naming the setting.

---

## API

Everything is mounted under `/api` except `/health`. `GET /api/foods` and the
register/login routes are public; every other route requires the session cookie, and the
`/api/admin/*` routes additionally require membership of `ADMIN_EMAILS`.

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/auth/register` | Create an account and sign in |
| `POST` | `/api/auth/login` | Sign in |
| `POST` | `/api/auth/logout` | Sign out |
| `GET` | `/api/auth/me` | Signed-in account info |
| `POST` | `/api/ask` | Knowledge-base question answering |
| `POST` | `/api/chat` | Routed assistant — retrieval, tools, or both |
| `GET` | `/api/foods` | Public food table, for the picker |
| `GET` `POST` | `/api/children` | List / create child profiles |
| `GET` `PUT` `DELETE` | `/api/children/{child_id}` | Read / replace / remove one profile |
| `GET` | `/api/children/{child_id}/targets` | Daily targets with note overrides and intake comparison |
| `GET` `POST` | `/api/children/{child_id}/feedings` | Recent feeds (`?days=`, default 14, max 90) / log one |
| `DELETE` | `/api/children/{child_id}/feedings/{feeding_id}` | Remove a logged feed |
| `GET` `POST` | `/api/children/{child_id}/growth` | Measurements with WHO assessment / record one |
| `DELETE` | `/api/children/{child_id}/growth/{measurement_id}` | Remove a measurement |
| `GET` | `/api/children/{child_id}/growth/curves` | WHO percentile curves for the charts |
| `GET` `POST` | `/api/admin/foods` | Every food including inactive / create one |
| `PUT` | `/api/admin/foods/{food_id}` | Edit a food; the id is immutable |
| `POST` | `/api/admin/foods/{food_id}/deactivate` \| `/activate` | Retire or re-offer a food (idempotent) |
| `POST` | `/api/admin/foods/import` | Bulk YAML/CSV import, all-or-nothing |
| `GET` | `/health` | Liveness plus dependency status |

### Asking a question

Sign in once into a cookie jar, then call the endpoint:

```bash
curl -s -c jar localhost:8000/api/auth/register -H 'content-type: application/json' \
  -d '{"email": "parent@example.com", "password": "correct horse battery"}'

curl -s -b jar localhost:8000/api/ask -H 'content-type: application/json' \
  -d '{"question": "How much iron does a 9-month-old need?", "strategy": "advanced", "stream": false}'
```

`/api/ask` requires a session because every call spends model credit, not because it
reads user data — it reads none and persists nothing.

### Chat

`POST /api/chat` takes `message`, `child_id`, `history` (up to twelve turns), `timezone`,
`strategy` and `stream`. `child_id` may be omitted only when the account has at most one
child; with more than one it is required. The body rejects unknown fields: the child's
details and the feeding log **cannot** be supplied by the client. The server loads both
from the account's own rows, so the stored profile is the only authority for the numbers
a plan is built from.

Any profile- or log-backed argument the model proposes is replaced with the stored value,
and the tool activity records that it was (`used_context`).

Streaming responses are server-sent events:

| Event | Carries |
|---|---|
| `route` | The intent and the planned capabilities |
| `tool` | One per invocation: name, status, validated arguments, `used_context`, result or a parent-facing error |
| `token` | Answer fragments |
| `final` | Citations with source and year, retrieval statistics, disclaimer, tool summary |
| `done` | End of stream |
| `error` | Terminal failure, with the `request_id` |

`"stream": false` returns the same content as one JSON object. A failed tool — unknown
food, missing height — becomes an error entry and the answer still completes.
`/api/ask` uses a shorter sequence: `token` fragments, then one `citations` event, then
`done`.

---

## Deterministic tools

Eleven tools live in `backend/tools/`. Each takes a Pydantic-validated input and never
asks the model for a number. `build_tools()` exposes them as LangChain structured tools;
the router binds all eleven plus a `search_guidelines` pseudo-tool that stands for
"consult the knowledge base". The pseudo-tool is intercepted rather than executed. At
most four tool calls run per message, in a single round — there is no agent loop.

| Tool | What it does | Source of the numbers |
|---|---|---|
| `calculate_bmi` | Weight over height squared | CDC definition |
| `assess_growth` | z-scores, percentiles and WHO bands for weight-for-age, length/height-for-age, weight-for-length/height and BMI-for-age. Indicators the inputs cannot support are skipped with a reason, never failed | WHO Child Growth Standards |
| `calculate_calorie_target` | Estimated Energy Requirement by age band; height and activity from 36 months | 2005 DRI EER equations |
| `calculate_protein_target` | Grams per kilogram by age band | DRI AI/RDA |
| `lookup_food` | One food's per-serving nutrients and safety flags, by id or plain name; with a quantity and unit the scaled figures too | `nutrition-data/foods.yaml` |
| `calculate_meal_nutrition` | Totals over a list of foods. Unknown foods are reported, never dropped | `nutrition-data/foods.yaml` |
| `generate_meal_plan` | Targets → doctor's-row overrides → diet filter → note avoidances → safety filter → composition → safety re-check → totals, disclaimer and audit record | all of the above |
| `log_feeding` | Validates one feed, prices it from the food table, assigns an id | `nutrition-data/foods.yaml` |
| `get_daily_nutrition` | One local day's totals from the feeding log | `nutrition-data/foods.yaml` |
| `get_remaining_targets` | The day's targets minus intake, floored at zero | DRI + food table |
| `detect_nutrient_gaps` | Rolling-window intake against targets, with a confidence level | DRI + food table |

### The food table

`nutrition-data/foods.yaml` is a hand-curated table of fifty-seven infant and toddler
foods with USDA FoodData Central figures per serving, carrying the major allergens and
the choking-hazard, honey and unpasteurised flags the safety filter reads.
The whole file is rejected if any entry is invalid.

The file seeds the database rather than being served directly: the live table lives in
`food_table_revisions` as whole-table snapshots, and every plan's audit record names the
exact revision it used.

### Growth standards

`nutrition-data/who-growth-standards.yaml` holds the WHO Child Growth Standards (2006)
LMS parameters per indicator, sex and completed month, generated from WHO's published
tables with a per-file URL, sha256 and retrieval date recorded. Rebuild with
`uv run --with openpyxl scripts/build_growth_tables.py`; the application reads only the
committed YAML and validates it whole at load.

### Doctor's notes

Note rows are extracted by the model in one pass into bounded structures — per row at
most one numeric target (calories, protein or iron; doctor rows only) and the plain
phrases of foods or food groups to avoid — and applied by plain Python. A target wins on
conflict and the conflict becomes an explicit entry in `overrides`. A phrase is resolved
in code to a food category or the specific table foods it names, and those foods are
excluded before the safety filter runs, with the row quoted as the reason.

Every row gets an outcome, so a phrase the table does not recognise is shown as *not
applied* rather than silently dropped. If extraction fails entirely, the plan is still
generated and every row is flagged.

---

## Daily targets, feeding log and gaps

`GET /api/children/{child_id}/targets` is the single source of truth for "what does this
child need in a day". It resolves the general age-band targets, applies the
doctor's-note overrides, and annotates each tracked nutrient with the fourteen-day
intake average, the ratio against target, and a below/adequate/above flag. Targets cover
calories, protein, iron, vitamin D, calcium, vitamin B12 and DHA; which of them are
*tracked* depends on the child's age and diet preference, and the rest are shown as
display-only with the reason. It returns the overrides alongside the numbers so the UI
can show what changed and why. No nutrient number is ever computed in the browser.

The feeding log stores one row per feed: a timezone-aware timestamp, a type from the
closed vocabulary `breastmilk | formula | solid | water`, a food from the table for
solids, and a quantity with unit. Breast milk may be logged without a quantity — direct
breastfeeding has no measure — in which case the entry contributes no nutrients and marks
its day *incomplete*. Nutrients are recomputed from the committed food table on every
read and never stored, so a correction to the table propagates to history.

`detect_nutrient_gaps` compares intake with the same note-overridden targets the planner
uses, so a prescribed calorie limit is never reported as a deficit. The window widens with
the number of *complete* days in the last fourteen: none yields `insufficient_data`, one
or two gives low confidence and direction only, three to six a three-day window at medium
confidence, seven or more a seven-day window at high confidence.

A gap report steers `generate_meal_plan`: a `below` flag at medium or high confidence
makes the composer favour foods dense in that nutrient. Targets are never raised and the
iron upper limit stays in force. Today's intake is subtracted so a plan covers the rest of
the day, and when under a tenth of the calorie target remains the plan reports
`targets_met` instead.

---

## Growth tracking

The profile stores a date of birth, so every age is derived on read — as of today for the
profile, as of the measurement day for a growth row. A birth date in the future or more
than sixty months back is rejected.

The growth log holds one row per child per calendar day: the date, the weight, and an
optional height. Every read recomputes each row's age and its WHO
assessment through the same arithmetic the chat uses; nothing derived is stored. Posting
the newest measurement by date also updates the profile's weight and height in the same
transaction, so targets and plans use the freshest numbers. A second measurement for the
same day is a conflict; one dated before the birth date is rejected.

The curves endpoint returns, for the child's sex, WHO percentile curves at every tenth
percentile from the 10th to the 90th, for each of the four indicators — months 0–60 for
the age-based ones, and every whole centimetre of the length or height table for
weight-for-length/height — computed by inverting the same LMS arithmetic and cached.
Measurements also carry a two-decimal exact age so points within one completed month
spread along the axis, while the assessment itself still uses completed months.

---

## Food table administration

The food table is data, not code. Accounts listed in `ADMIN_EMAILS` see a **Food table**
link in the app header and can reach `/admin/foods`; everyone else gets a refusal there
and `403` from the routes.

Every write — create, edit, deactivate, reactivate, import — loads the latest snapshot,
applies the change in memory, validates the whole table with the same model that
validates the YAML file, and inserts the next revision with the actor and a summary. Two
concurrent writers cannot both win. The served table is swapped in-process on each write,
so the picker, the lookup tools and the planner see the change immediately.

Bulk import takes YAML or CSV with an `upsert` or `create_only` mode and a dry-run flag.
It reports created, updated and unchanged ids plus per-row errors; a file with any bad
row writes nothing.

Foods are never deleted. A deactivated food leaves the picker, name resolution and every
new plan, but stays retrievable by id so feeds already logged against it keep their
nutrients. Breast milk and iron-fortified formula cannot be deactivated. Every entry needs
an explicit source and explicit answers to the three safety questions — the form
preselects nothing — and a minimum age of zero is allowed only for milk feeds.

---

## External food lookup

When a parent asks about a food the internal table does not have, the assistant may fetch
it live from a whitelisted source. This is **disabled by default** and is deliberately
constrained:

- **Whitelist by exact hostname** (`EXTERNAL_FOOD_DOMAINS`), never a URL the code
  assembles. USDA FoodData Central is tried first, then MyFoodData. An empty whitelist
  allows nothing.
- **Triggered only on an internal-table miss**, inside the chat request, with a timeout
  and a bounded cache. A failure of any kind — disabled, unconfigured, not whitelisted,
  not found, network error — returns nothing rather than raising.
- **Parsed by deterministic code.** The model never generates or restates a number from
  the response.
- **Visibly distinct from a guideline citation.** It renders as a separately styled card
  with the source, a link, the retrieval timestamp and its own disclaimer — third-party
  nutrition data is not a pediatric guideline.
- **Never usable in a meal plan.** The fetched data carries no allergen, choking-hazard,
  honey, pasteurisation or minimum-age metadata, so it cannot pass the safety filter.

An administrator viewing such a card additionally gets an inline action to add the food
for real. It opens the normal food form prefilled with the fetched figures; the admin must
supply every missing safety field themselves — these are never fetched and never inferred
— and the write goes through the existing `/api/admin/foods` pipeline unchanged, with the
same validation, versioning and authorisation. There is no parallel write path.

No other outbound third-party call is permitted anywhere in the request path.

---

## The interface

The signed-in app is one screen: a four-tab side panel and a chat widget.

- **Child** — the profile form (birth date, sex, weight, height, activity level,
  allergens, diet preference) and the note rows, plus any "couldn't apply" outcomes from
  the most recent plan.
- **Feeding log** — today's summary, the log-a-feed form with a food picker, and entries
  grouped by local day.
- **Daily targets** — the resolved targets, an overrides callout naming each nutrient a
  doctor's row changed and what it changed from, and a progress bar per tracked nutrient.
- **Growth** — the measurement form, four inline-SVG percentile charts, and one indicator
  row per WHO assessment.

Chat is a floating panel launched from the corner. It stays mounted while hidden, so a
half-typed question and the scroll position survive being closed. Each assistant message
shows the intent, one chip per tool (expandable to its arguments and result), a structured
meal-plan card when a plan was generated — with a banner per nutrient a doctor's row
overrode — the answer with numbered citation markers, the sources list with publication
years, and the disclaimer.

Public pages at `/`, `/about`, `/recipes` and `/contact` carry the marketing copy. All
parent-facing wording lives in `frontend/src/lib/copy.ts` and `backend/chat/copy.py`: warm
by default, direct about safety and errors.

The browser only ever talks to the Next.js origin. `/api/*` is rewritten server-side to
`BACKEND_URL`, so the session cookie stays same-origin.

---

## Knowledge base

The corpus lives in `knowledge-base/` as hand-condensed Markdown summaries of recognised
pediatric guidelines. `manifest.yaml` carries each document's citation metadata: source
title, publication year, topic, authority, applicable age range in months, and URL.

```bash
uv run scripts/ingest.py    # embed new or changed documents (idempotent)
```

Ingestion is incremental. It hashes every document, compares against what the vector
store already holds, and re-embeds only what changed, replacing each document's chunks as
a unit. Re-running with no changes embeds nothing.

**To add a source:** drop a `.md` file in `knowledge-base/` using `## Section` headings —
chunks record the nearest heading for citations — add a manifest entry, and re-run the
script. Changing `EMBEDDING_MODEL` requires deleting the vector store and re-ingesting;
it refuses to search a collection built with a different model.

---

## Security

Sign-in is email and password, hashed with argon2id. The session is a signed token in an
`HttpOnly`, `SameSite=Lax` cookie, so the browser never handles a token and a cross-site
form post carries neither the cookie nor an acceptable content type.

`backend/api/deps.py` holds the two dependencies every user-scoped route runs behind:
`get_current_user`, which returns `401` without a valid session and refuses a deactivated
account on its next request, and `owned_child`, the single place the ownership predicate
is written. A non-owner gets the same `404` as a nonexistent id, so probing learns
nothing. `require_admin` gates the admin routes on `ADMIN_EMAILS`.

`tests/test_api_children.py` is the evidence: owner-only listing, byte-identical `404`s
for non-owner and nonexistent ids, and a loop over the OpenAPI schema asserting every
user-scoped operation returns `401` without a cookie.

**Abuse ceilings.** The model-spending routes share one budget, the credential routes
another, and the food-table writes a third. Each answers `429` with a `Retry-After`
header before any retrieval, model call or password hashing happens. The limiter is
in-process, which is exact because the service runs as a single instance. Cross-origin
browser access is an explicit allowlist and is empty by default.

**Never logged:** passwords, password hashes, session tokens, cookies, request headers,
email addresses, the client address, and the text of either the parent's message or the
assistant's answer — only the message length. Records carry `user_id` and
`child_profile_id`, never emails. The doctor's note stays in the meal-plan audit snapshot
because auditability requires it, and `AUDIT_LOG_PATH` lets those records be kept
separately. `tests/test_api_auth.py::TestNothingSensitiveIsLogged` registers and signs in
with every logger at `DEBUG` and asserts none of that material appears.

---

## Logging and monitoring

Every record is one line — a JSON object by default, or readable text. Every record
emitted while handling a request carries the same three correlation fields: `request_id`,
`user_id` and `child_profile_id`. Nothing in `backend/tools/` or `backend/nutrition/`
knows about any of this: the values live in context variables set by the middleware and
the auth dependencies, and a logging filter stamps them onto each record.

| Logger | One record per | Fields |
|---|---|---|
| `backend.api.access` | request | `method`, `route` template, `status`, `latency_ms`, `user_id` |
| `backend.chat.router` | chat message | intent, planned and executed capabilities with outcomes, retrieval stats, `message_chars`, `latency_ms` |
| `backend.chat.tools` | tool invocation | `tool`, `status`, `latency_ms`, `used_context`, `error_kind` |
| `backend.rag.pipeline` | retrieval | `strategy`, `queries`, `retrieved`, `kept`, `top_score`, `latency_ms` |
| `backend.tools.audit` | meal plan / gap detection | the full input snapshot as JSON |
| `backend.api.errors` | unhandled exception | traceback; the client gets `500` with a `request_id` and never a traceback |

Every response carries `X-Request-ID`, honouring a well-formed incoming one so a proxy's
id threads through. To follow one request end to end:

```bash
uv run uvicorn backend.main:app --port 8000 --no-access-log > app.log
curl -si localhost:8000/api/foods | grep -i x-request-id
grep '"request_id": "<the id>"' app.log
```

---

## Testing

```bash
uv run pytest                    # backend suite; excludes integration tests
uv run pytest -m integration     # live OpenRouter and vector-store tests; spends credit
uv run ruff check . && uv run ruff format --check backend tests scripts
pnpm -C frontend lint && pnpm -C frontend typecheck && pnpm -C frontend test
```

Two markers matter. `integration` needs live external services and real credit, and is
excluded by default. `db` needs the Docker Compose PostgreSQL through
`TEST_DATABASE_URL` — a separate database the fixtures create and drop, so they can never
touch development data. When it is unset those tests skip; when it is set but unreachable
they fail.

Migrations are hand-written and round-trip: `uv run alembic downgrade base && uv run
alembic upgrade head` is exercised by `tests/test_migrations.py`, including the backfill
that derives each profile's birth date.

CI runs on every push and pull request to `main`: lint, format check and the backend suite
with a dummy database URL (so `db` tests skip and nothing is spent), and lint, typecheck,
tests and a production build for the frontend.

---

## Deployment

The API ships as a Docker image, the frontend as a separate Next.js project, and the
database is managed. There is no orchestration layer: one API instance, by design.

### The API image

`Dockerfile` builds the API only. uv installs dependencies from the committed lockfile at
build time and the runtime never calls it. The image carries the backend, the migrations,
the ingestion script, the knowledge base and the nutrition data, and runs as a non-root
user. `.dockerignore` keeps the frontend, tests, evals, local tooling, `.env` files and
any local vector store out of it.

```bash
docker build -t nutrition-api .
docker run --rm -p 8000:8000 --env-file .env nutrition-api
```

### Start sequence

`scripts/start.sh` runs three steps, and a failure in either preparatory step stops the
container before it serves a single request:

1. `alembic upgrade head` — bring the schema to head.
2. `python scripts/ingest.py` — embed anything new or changed in the corpus.
3. `exec uvicorn backend.main:app` — with the hosting proxy trusted for the client
   address and uvicorn's own access log off.

Trusting `X-Forwarded-For` is what lets the rate limiter key on the real client address,
and it is only safe when a proxy is the sole peer that can reach the container. **Never
expose this image directly on a public interface.**

### Render blueprint

`render.yaml` declares one Docker web service (`nutrition-api`) and one managed
PostgreSQL database (`nutrition-db`), auto-deploying from `main` and health-checked at
`/health`.

`numInstances: 1` is deliberate, not a placeholder: the rate limiter is in-process, and
the start script migrates before serving. Scaling out would need a shared limiter and the
migration lifted out of the container.

`SESSION_SECRET` is generated on first deploy. `OPENROUTER_API_KEY` and `ADMIN_EMAILS` are
marked `sync: false` — entered in the dashboard, never committed. `ALLOWED_ORIGINS` stays
empty because the browser reaches the API through the frontend's same-origin rewrite, so
no cross-origin grant is needed.

**Persistent disk.** `MILVUS_DB_PATH` points at `/data`, but the disk block is commented
out because Render offers disks on paid plans only. Without it the twenty-document corpus
is re-embedded on every start — quick, but it spends embedding credit each time.
Uncomment the block to keep the vector store across deploys.

### Frontend

A separate Vercel project with root directory `frontend/` and one environment variable,
`BACKEND_URL`, pointing at the API service. Vercel rewrites `/api/*` server-side, so the
browser only ever talks to the frontend origin and the session cookie stays same-origin.

### Before the first deploy

With `APP_ENV=prod` the application refuses to start without `SESSION_SECRET` or
`OPENROUTER_API_KEY`, failing loudly at boot rather than serving `503`s. Set both, plus
`ADMIN_EMAILS` if anyone needs the food-table role, and `BACKEND_URL` on Vercel.

---

## Evaluation

`evals/` is a **separate uv project** — the evaluation library pins an older LangChain
than the application runs — that treats the running service as a black box over HTTP. See
[`evals/README.md`](./evals/README.md).

It runs a reviewed 55-case test set across seven categories (basic and advanced
knowledge-base questions, tool, hybrid, user-data, out-of-domain and adversarial) through
both retrieval strategies, and scores three ways: deterministic retrieval, routing and
safety checks; RAGAs generation metrics (faithfulness, answer relevancy, context
precision, context recall); and a per-category breakdown.

```bash
uv run --project evals python -m harness.run --skip-judge     # deterministic layers only, no spend
uv run --project evals python -m harness.run --label baseline # full A/B with the judge
```

The recorded baseline in [`evals/reports/`](./evals/reports/) found `basic` and `advanced`
tied on every deterministic check — full retrieval hit rate and citation provenance, and
correct refusal on every out-of-domain and adversarial probe — and within noise of each
other on the generation metrics, with `advanced` slightly slower. `tests/test_eval_cases.py`
in the main suite keeps the case file valid without needing the evals environment.

---

## Notes for contributors

- LangChain resolves to 1.x and `pymilvus` to 3.x. Both are past major-version breaks from
  the APIs most tutorials still show — check the current documentation rather than
  pattern-matching from older examples.
- Keep AI logic out of HTTP concerns. FastAPI owns routing, auth boundaries, streaming and
  validation; `backend/nutrition/` is pure Python with no model or database calls.
- If you add a nutrient number anywhere, it belongs in a lookup table or a documented
  reference equation — never in a prompt.

## Further reading

- [`CLAUDE.md`](./CLAUDE.md) — working context for AI coding assistants: stack,
  architecture principle, hard rules.
- `Nutrition_App_Full_Reference.md` — the long-form specification: full rationale, RAG
  strategy, evaluation design, and the production migration path.
