## Why

Reference §15 and §17 commit Day 7 to a *deployed* MVP: a container for FastAPI on managed
hosting, managed PostgreSQL through the same `DATABASE_URL`, and the Next.js app on Vercel.
Today nothing is deployable — there is no Dockerfile, no start sequence that runs the
migrations and builds the knowledge base before serving, and no deployment descriptor — and
three things that were acceptable on `localhost` are not on a public URL: `POST /api/ask`
spends OpenRouter credit for anyone who finds it, no route has a request rate limit (the
sign-in route included), and a production instance with a missing `SESSION_SECRET` boots
quietly and answers 503 per request instead of refusing to start. Every user-scoped
operation already sits behind the session (hard rule 9, Day 6); this change closes the
remaining gaps between "works on my machine" and "safe to leave running".

**Scope: [MVP]. Day 7 of 7, first workstream** — before the request-id UI polish, the eval
follow-ups, and the `[Stretch]` growth assessment. Time-box: half a day for the code, the
rest of the morning for the two hosting consoles. Developed on `main`.

## What Changes

- **`POST /api/ask` requires a session.** **BREAKING** for anonymous callers: the route
  gains the same `CurrentUser` dependency as `/api/chat` and answers 401 with the fixed
  message without a valid cookie. It still reads no child data and persists nothing; the
  session exists to bound who can spend model credit. The evaluation harness — the only
  known anonymous caller — registers its throwaway account before the knowledge-base cases
  too, not only before the chat cases. The frontend never calls `/api/ask` and is unchanged.
- **Per-client request rate limits.** A small in-process fixed-window limiter, keyed by
  client address, on the two route groups that cost something: the model-spending routes
  (`/api/ask`, `/api/chat`) and the credential routes (`/api/auth/register`, `/login`).
  Over the limit answers 429 with a `detail` message and a `Retry-After` header. Limits are
  settings (`RATE_LIMIT_MODEL_PER_MINUTE`, `RATE_LIMIT_AUTH_PER_MINUTE`; `0` disables).
  Behind the hosting proxy the client address comes from `X-Forwarded-For`, which uvicorn is
  told to trust (`--proxy-headers`); on the host it is the socket peer as today.
- **An explicit cross-origin policy.** `ALLOWED_ORIGINS` (comma-separated; default empty)
  drives Starlette's `CORSMiddleware` with credentials allowed. Empty means what the browser
  already enforces today — no cross-origin access; the API is reached through the Next.js
  same-origin `/api` rewrite — but the policy is now stated and testable rather than implied.
- **Production configuration is checked at startup.** With `APP_ENV=prod` the application
  refuses to start, naming the setting, when `SESSION_SECRET` or `OPENROUTER_API_KEY` is
  absent. In `dev` and `test` the current boot-anyway-and-report behaviour is unchanged
  (`/health` still answers, authenticated routes still 503).
- **A container image and start sequence.** `Dockerfile` (`python:3.14-slim`, dependencies
  installed by `uv sync --frozen --no-dev` from the committed lockfile, non-root user) and
  `scripts/start.sh`: `alembic upgrade head` → `scripts/ingest.py` (re-runnable; embeds only
  what changed) → uvicorn with `--proxy-headers --no-access-log`. Milvus Lite lives at
  `MILVUS_DB_PATH` (a mountable `/data` directory) and is rebuilt on an empty disk.
- **Deployment descriptors and docs.** `render.yaml` blueprint (Docker web service + managed
  PostgreSQL, `/health` as the health check, every environment variable listed), Vercel
  settings for the frontend recorded in `README.md` (root `frontend`, `BACKEND_URL`), a
  "Deployment" README section, `.env.example` entries for the new settings, and the README
  status line flipped from "Day 6 of 7" to deployed with the live URLs.
- **A minimal GitHub Actions workflow** (`§15: Docker, GitHub, GitHub Actions`) running
  `ruff`, the offline `pytest` suite, and the frontend lint/typecheck/test/build on push and
  pull request. Last task; cut first if the morning runs long.

## Capabilities

### New Capabilities

- `production-hardening`: what a deployed instance must do that a development instance need
  not — per-client request rate limits on the model-spending and credential routes, the
  proxy-aware client address, the explicit cross-origin policy, production configuration
  validated at startup, and the container's start sequence (migrate, ingest, serve).

### Modified Capabilities

- `ask-api`: *The endpoint is not user-scoped* becomes *The endpoint requires a session but
  is not user-scoped* — a valid session is required (401 otherwise, no retrieval or model
  call), while the endpoint still reads no child data, persists nothing, and takes no
  identity from the body.
- `rag-evaluation`: *Both strategies are evaluated through the running service* — the
  knowledge-base cases are sent to the question endpoint under the account the evaluation
  registers for itself, not to a public endpoint.

## Impact

- **New code**: `backend/api/rate_limit.py` (limiter + route dependency),
  `Dockerfile`, `.dockerignore`, `scripts/start.sh`, `render.yaml`,
  `.github/workflows/ci.yml`, `tests/test_rate_limit.py`.
- **Touched code**: `backend/api/ask.py` (`CurrentUser` + limiter dependencies),
  `backend/api/chat.py` and `backend/api/auth.py` (limiter dependency), `backend/api/router.py`
  (docstring: what is public), `backend/main.py` (CORS middleware, limiter on `app.state`,
  production guard), `backend/core/config.py` (`allowed_origins`, the two rate-limit fields,
  production validation), `evals/harness/run.py` (register before any case), `.env.example`,
  `README.md`, `tests/test_api_ask.py` (authenticated client), `tests/test_app.py`
  (`/api/ask` moves from the public set to the user-scoped set), `tests/test_config.py`.
- **Untouched**: `backend/chat/`, `backend/rag/`, `backend/tools/`, `backend/nutrition/`,
  prompts, corpus, the Alembic chain, every request/response model, the frontend.
- **API surface**: `/api/ask` now 401s without a session; 429 with `Retry-After` is a new
  possible answer on five routes; CORS headers appear only for configured origins.
- **Dependencies**: none. `CORSMiddleware` ships with Starlette; the limiter is a dict and a
  clock. The image adds `uv` from its official image at build time only.
- **Operations**: one Render web service and one Render PostgreSQL, one Vercel project.
  Environment on Render: `DATABASE_URL` (from the database), `APP_ENV=prod`,
  `SESSION_SECRET`, `OPENROUTER_API_KEY`, `LOG_FORMAT=json`, `MILVUS_DB_PATH=/data/milvus.db`,
  `ALLOWED_ORIGINS` (empty), the two rate limits. On Vercel: `BACKEND_URL`.

## Non-goals

- **A distributed rate limiter (Redis) or per-account quotas** — the service runs as one
  process on one instance; a per-process limiter is exact there. Per-account token budgets
  are a cost-dashboard concern, [Stretch] per §17.
- **Keeping `/api/ask` public with a limiter only** — considered; sign-in was chosen because
  a per-IP limit alone still lets any anonymous client spend credit steadily, and the only
  legitimate anonymous caller (the eval harness) already knows how to register.
- **Rate-limiting `/api/foods`, `/api/children`, and the feeding log** — cheap, user-scoped,
  and already bounded by the session.
- **A persistent Milvus disk as a requirement** — the start sequence rebuilds a 20-document
  corpus in seconds of embedding spend; a mounted `/data` makes that a no-op but is optional.
- **Container images for the frontend or the database** — Vercel builds Next.js; the
  database is managed. `docker-compose.yml` stays a development database only.
- **Kubernetes, Celery, CDN, custom domains, blue/green deploys** — out of scope entirely
  (CLAUDE.md).
- **Showing the request id in the UI, the three eval findings, the growth assessment** —
  the rest of Day 7, each its own change or polish commit after this one is live.
