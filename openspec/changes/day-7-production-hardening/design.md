## Context

See proposal.md — Why. What shapes the approach: the authorization surface is two
dependencies in `backend/api/deps.py` and the route-surface test in `tests/test_app.py`
enumerates exactly which paths are public (`PUBLIC_PATHS`) and which refuse without a
session (`USER_SCOPED_PATHS`), so moving a route across that line is a one-set edit with a
test that fails until the route agrees. `RequestContextMiddleware` (`backend/api/middleware.py`)
is a pure ASGI callable that owns the request id, the access record, and the last-resort 500;
anything that answers a request itself must sit inside it to keep those guarantees.
`create_app()` already tolerates an unconfigured `Settings` (`_settings_if_configured()`
returns `None`), because the app must boot and answer `/health` with no database — the new
settings must not break that. The eval harness (`evals/`) is a separate uv project that
talks to the service only over HTTP through one `httpx.Client` whose cookie jar already
carries the session from `register()` to every later call. The browser reaches the API only
through the Next.js rewrite (`frontend/next.config.ts`), so cookie, CORS, and streaming all
ride on one origin. The service will run as one process on one Render instance behind
Render's TLS-terminating proxy, with `PORT` injected; Milvus Lite is a file.

## Goals / Non-Goals

**Goals:** no anonymous model spend; a hard per-client ceiling on model and credential
routes; a stated cross-origin policy; a production instance that fails loudly at boot when
mis-configured; an image that goes from empty to serving with no manual step; every
existing test still green with the smallest edits.

**Non-Goals (design-level):** any change to `RequestContextMiddleware`'s behaviour, to the
session token, to the Alembic chain, or to the frontend; any new Python dependency; a
limiter that survives a restart or spans instances.

## Decisions

### 1. `/api/ask` takes `CurrentUser`; nothing else about it changes

**Decision:** add `user: CurrentUser` to `ask()` in `backend/api/ask.py` and do not use it
beyond the dependency. `get_current_user` already sets `user_id` in the request context, so
ask records become account-correlated for free (observability spec). The route moves from
`PUBLIC_PATHS` to `USER_SCOPED_PATHS` in `tests/test_app.py`, which makes the OpenAPI loop
assert the 401 and its body. `tests/test_api_ask.py` keeps its database-free `TestClient` by
overriding `get_current_user` with a stub returning a `User` built in memory (the same
pattern `test_api_chat.py` uses for `resolve_chat_request`), plus one test without the
override asserting 401 and that the fake LLM recorded no call.

**Why:** the session is the one identity primitive the codebase has; reusing it means the
spend boundary and the data boundary are the same code path, and hard rule 9's "byte-identical
401" holds on this route too. The alternative — an API key for the eval harness plus a public
limiter — adds a second credential type for one caller.

**Eval harness:** in `evals/harness/run.py`, `require_database()` and `register()` run
unconditionally before the first case (registration needs the database anyway). No client or
scoring change; `evals/tests/test_client.py` already exercises cookie reuse from `register()`
to `ask()`.

### 2. An in-process fixed-window limiter as a FastAPI dependency, not middleware

**Decision:** `backend/api/rate_limit.py` provides `RateLimiter` (a dict
`(bucket, client) → (window_start, count)` with a monotonic clock, pruned on access) and a
dependency factory `rate_limited(bucket: Literal["model", "auth"])` that reads the limiter
from `request.app.state.rate_limiter`, the client address from `request.client.host`, and
raises `HTTPException(429, detail=copy.RATE_LIMITED, headers={"Retry-After": seconds})`.
The limiter is built once in `create_app()` from settings (or defaults when `Settings` is
unconfigured). Routes declare it: `ask` and `chat` with `"model"`, `register` and `login`
with `"auth"`. Dependencies run before the body-bound ones that would do work, so a 429 costs
nothing downstream.

**Why a dependency:** FastAPI turns the `HTTPException` into the standard `{"detail": …}`
body the frontend's `readDetail` already renders, the middleware still stamps the request id
and writes the access record with status 429, and the routes that are limited are visible in
the route signature rather than in a path-prefix table. A fixed window (not a token bucket)
is enough for a ceiling on abuse and is three lines to reason about.

**Why not `slowapi`:** a dependency on a library whose Python 3.14 status is untested this
morning, for a per-process limiter we can write in forty lines; it also keys on the request
in ways that fight the existing middleware ordering.

**Why per app instance:** every test fixture calls `create_app()` per test (`client`,
`make_client`, `api_client`), so counters start at zero per test and no test needs to reset
anything; `TestClient`'s peer address is constant, which is what the "over the limit" test
relies on, using a `Settings` with a limit of 2.

### 3. The client address comes from uvicorn's proxy handling, not from our code

**Decision:** the container starts uvicorn with `--proxy-headers --forwarded-allow-ips="*"`,
so `scope["client"]` is rewritten from `X-Forwarded-For` before the app sees it and
`request.client.host` is the real client on Render and the socket peer on a laptop. The
limiter never parses headers. The address is used as a dict key and never logged (the
observability "never logged" list gains "client address" in the README; the code simply
never puts it in `extra`).

**Why:** on Render the only peer that can reach the container is Render's proxy, so trusting
every forwarder is exact there; parsing `X-Forwarded-For` ourselves would have to answer
"which hop do we trust" and get it wrong on the host. `docker-compose.yml` and the README
development commands do not pass the flags, so nothing changes locally.

### 4. CORS is Starlette's middleware with an allowlist that defaults to nothing

**Decision:** `Settings.allowed_origins: list[str]` parsed from a comma-separated
`ALLOWED_ORIGINS` (blank → `[]`). `create_app()` adds `CORSMiddleware(allow_origins=…,
allow_credentials=True, allow_methods=["*"], allow_headers=["*"])` **before**
`RequestContextMiddleware` in code, which puts it *inside* the context middleware at
runtime (Starlette applies `add_middleware` outermost-last), so preflight responses also
carry `X-Request-ID` and an access record.

**Why:** with an empty allowlist the middleware emits no CORS headers, which is exactly the
browser's default denial the service relies on today via the same-origin rewrite — the
change is documentation-made-code plus the ability to point a differently hosted frontend at
the API later without a code change. `allow_credentials=True` with `["*"]` origins is invalid
CORS, and the setting's validator rejects `*` to keep that mistake out of an environment
variable.

### 5. Production guard in `Settings`, raised from `create_app()`

**Decision:** `Settings` gains a `model_validator(mode="after")`: when `app_env == "prod"`
and `session_secret is None`, raise `ValueError("SESSION_SECRET is required when
APP_ENV=prod")`; `create_app()` additionally checks `get_rag_settings().openrouter_api_key`
under `prod` and raises `RuntimeError` naming `OPENROUTER_API_KEY`. In `prod`, a
`ValidationError` from `Settings` is therefore not swallowed by `_settings_if_configured()`:
that helper re-raises when the environment variable `APP_ENV` is `prod` (read directly,
since `Settings` did not construct).

**Why:** the Day 6 design chose "boot and report" so a laptop without a database still gets
`/health`; on Render a missing secret means every authenticated route is a 503 forever and
the deploy still shows green. Failing at import makes Render's deploy fail with the setting's
name in the log. The rule lives on `Settings` so `tests/test_config.py` covers it without an
app; the provider-key check lives in `create_app()` because `RAGSettings` deliberately never
fails to construct.

### 6. Image: `python:3.14-slim`, `uv sync --frozen --no-dev`, venv on `PATH`, no `uv` at runtime

**Decision:** two-stage-in-one Dockerfile: copy `uv` from `ghcr.io/astral-sh/uv:0.9`
(pinned), `COPY pyproject.toml uv.lock`, `uv sync --frozen --no-dev --no-install-project`
(dependency layer cached across source changes), then `COPY backend alembic alembic.ini
scripts knowledge-base nutrition-data`, `ENV PATH=/app/.venv/bin:$PATH`, a non-root `app`
user owning `/app` and `/data`, `EXPOSE 8000`, `CMD ["scripts/start.sh"]`. `.dockerignore`
excludes `.env*`, `milvus.db*`, `frontend/`, `node_modules/`, `evals/`, `.venv/`, `tests/`,
`openspec/`, `.git/`. `scripts/start.sh` (`set -euo pipefail`): `alembic upgrade head`,
`python scripts/ingest.py`, `exec uvicorn backend.main:app --host 0.0.0.0 --port "${PORT:-8000}"
--proxy-headers --forwarded-allow-ips="*" --no-access-log`. `MILVUS_DB_PATH` defaults to
`/data/milvus.db` in the image (`ENV`), so a Render disk mounted at `/data` persists the
vector store and an unmounted `/data` is simply rebuilt.

**Why:** the lockfile is authoritative (CLAUDE.md) and `--frozen` enforces it; the venv
`uv sync` produces is the same interpreter environment `uv run` would select, so calling
`alembic`/`uvicorn` from it directly avoids `uv` resolving at every container start and keeps
`uv` out of the runtime image. `uvicorn[standard]` is already a dependency, so `uvloop` and
`httptools` come for free. `pymilvus[milvus-lite]` ships a Linux x86_64 wheel that works on
`slim`. The project itself is not installed (`--no-install-project`) because `backend` is
imported from the working directory, as it is on the host.

**Why ingest at start rather than at build:** ingestion needs `OPENROUTER_API_KEY`, which
must not be baked into an image layer; and the corpus is 20 documents, ~100 KB — a full
rebuild is seconds and cents. `scripts/ingest.py` is already incremental, so with a mounted
disk a restart embeds nothing.

### 7. Render blueprint + Vercel project; the frontend proxies as it does locally

**Decision:** `render.yaml` declares one Docker web service (`healthCheckPath: /health`,
`autoDeploy: true` from `main`) and one PostgreSQL database; `DATABASE_URL` uses
`fromDatabase.property: connectionString` (Render's internal URL — no TLS negotiation, and
`backend/core/config.py` already normalises the `postgres://` scheme to asyncpg);
`SESSION_SECRET` uses `generateValue: true`; `OPENROUTER_API_KEY` is `sync: false` (entered
in the console, never in the file). Vercel builds `frontend/` with `BACKEND_URL` set to the
Render URL; the rewrite in `next.config.ts` is unchanged, so the cookie is set on the Vercel
origin and `SameSite=Lax` + `Secure` hold.

**Why one origin:** moving the browser to talk to Render directly would make the session
cookie third-party and break sign-in without a shared parent domain we do not have.

### 8. Tests stay database-free where they were

**Decision:** `tests/test_rate_limit.py` uses `create_app()` with `Settings(..., rate_limit_
model_per_minute=2, _env_file=None)` injected through a small seam — `create_app(settings=
None)` gains an optional parameter used only by tests — and `TestClient`; `/api/foods`
is not limited and serves as the control. CORS tests send `OPTIONS` with `Origin` and
`Access-Control-Request-Method` and check the grant header's presence/absence. The
container is verified by hand in tasks (build, run against compose Postgres, `/health`), not
by pytest.

## Risks / Trade-offs

- [SSE through Vercel's external rewrite could be buffered or cut at a proxy timeout] →
  verify on the live URL that `token` events arrive incrementally and a long meal-plan
  answer completes; fallback is to host the Next.js server on Render as a second web
  service (Node runtime, same rewrite), which streams like `next dev` does locally.
- [`--forwarded-allow-ips="*"` on a host that is not behind a proxy lets a client spoof its
  address] → the flags are only in `scripts/start.sh` (the container), never in the README
  development command; documented in the Dockerfile comment.
- [Fixed window allows up to 2× the limit across a window boundary] → acceptable for an
  abuse ceiling; the numbers are settings.
- [The eval harness now registers an account on every run, including knowledge-base-only
  runs] → accounts are throwaway and already accumulate from chat runs; no cleanup change.
- [Render free-tier instances sleep; the first request after idle re-runs `start.sh`
  (migration no-op, ingestion no-op with a disk, full re-embed without one)] → document; a
  paid instance or a mounted disk removes it.
- [`alembic upgrade head` at start with two instances would race] → one instance by
  design; noted in `render.yaml` (`numInstances: 1`).
- [Moving `/api/ask` behind auth breaks any external caller we do not know about] → the
  README and the spec both said public; the only caller in the repo is the harness, which is
  fixed in the same change.

## Migration Plan

1. Merge the code and descriptors on `main` with all tests green.
2. Create the Render blueprint from `render.yaml`; enter `OPENROUTER_API_KEY` in the
   console; first deploy runs the migration and ingestion; confirm `/health` →
   `database: reachable`, `app_env: prod`.
3. Create the Vercel project on `frontend/` with `BACKEND_URL`; confirm sign-up, chat with a
   tool call, and streaming on the live URL.
4. Run the eval harness against the live URL with `EVAL_BASE_URL` (`--skip-judge`) to prove
   the authenticated question path from outside.
5. Rollback: Render "rollback to previous deploy" restores the prior image; the Alembic
   chain has no new revision in this change, so no schema rollback is involved.
