Developed on `main`. Time-box: half a day for groups 1–5, the rest of the morning for
groups 6–7 (hosting consoles); group 8 is the cut line. No request/response model changes;
no change to `backend/chat/`, `backend/rag/`, `backend/tools/`, `backend/nutrition/`, the
Alembic chain, or the frontend. Authorization boundary for the one user-facing behaviour
change: `/api/ask` takes identity only from `get_current_user` (the session cookie), uses it
for nothing but admission, and still reads no child data and persists nothing — the
route-surface test in `tests/test_app.py` is the evidence.

## 1. Settings and production guard

- [x] 1.1 Add to `Settings` in `backend/core/config.py`: `allowed_origins: list[str]`
  parsed from comma-separated `ALLOWED_ORIGINS` (blank → `[]`, entries stripped, `*`
  rejected), `rate_limit_model_per_minute: int = 30` and `rate_limit_auth_per_minute: int
  = 10` (both `ge=0`), and an after-validator that raises `ValueError` naming
  `SESSION_SECRET` when `app_env == "prod"` and the secret is unset; document all three
  in `.env.example`; verify `tests/test_config.py` covers blank/absent origins → `[]`, two
  origins with spaces → stripped list, `*` rejected, a negative limit rejected, the prod
  guard raising with the setting's name, and `dev` without a secret still constructing
- [x] 1.2 In `backend/main.py`, make `_settings_if_configured()` re-raise when the
  `APP_ENV` environment variable is `prod`, and have `create_app()` raise `RuntimeError`
  naming `OPENROUTER_API_KEY` when `app_env == "prod"` and `get_rag_settings()
  .openrouter_api_key` is `None`; add an optional `settings: Settings | None = None`
  parameter to `create_app()` used in place of `get_settings()` when given (tests only);
  verify `tests/test_app.py` shows `create_app()` raising with each setting's name under
  `APP_ENV=prod` (monkeypatched environment) and booting with `/health` → 200 under `dev`
  with neither configured

## 2. Rate limiter

- [x] 2.1 Create `backend/api/rate_limit.py`: `RateLimiter(limits: dict[str, int],
  window_seconds=60, clock=time.monotonic)` with `check(bucket, client) -> int | None`
  returning seconds to wait when over the limit (0 disables a bucket; stale entries pruned
  on access), and `rate_limited(bucket)` returning a FastAPI dependency that reads
  `request.app.state.rate_limiter` and `request.client.host` and raises `HTTPException(429,
  detail=copy.RATE_LIMITED, headers={"Retry-After": …})`; add `RATE_LIMITED` to
  `backend/chat/copy.py` (direct voice, no client address); verify unit tests in
  `tests/test_rate_limit.py` with an injected clock show N allowed then the (N+1)th refused
  with a positive wait, two clients independent, the next window admitting again, and 0
  never refusing; `tests/test_chat_copy.py` passes
- [x] 2.2 Build the limiter in `create_app()` from settings (defaults when unconfigured) onto
  `app.state.rate_limiter`; declare `Depends(rate_limited("model"))` on `ask` and `chat`
  and `Depends(rate_limited("auth"))` on `register` and `login`, positioned before the
  body/DB dependencies; verify in `tests/test_rate_limit.py` with `create_app(settings=
  Settings(..., rate_limit_model_per_minute=2, rate_limit_auth_per_minute=2, _env_file=
  None))` and `TestClient`: the third `/api/chat` post is 429 with `{"detail": …}`, a
  `Retry-After` header, an `X-Request-ID` header, and an access record with status 429 in
  `caplog`; the third `/api/auth/login` is 429 before any hashing (a `verify_password`
  spy is not called) with identical bodies for a known and an unknown email; `/api/foods`
  is never limited; and the 429 body and access record contain no client address

## 3. `/api/ask` behind the session

- [x] 3.1 Add `user: CurrentUser` to `ask()` in `backend/api/ask.py` (unused beyond
  admission), update the module docstring and the route docstring, and rewrite the
  "Public:" paragraph in `backend/api/router.py`; move `/api/ask` from `PUBLIC_PATHS` to
  `USER_SCOPED_PATHS` in `tests/test_app.py`; verify `TestRouteSurface` passes — the OpenAPI
  loop now asserts `/api/ask` answers 401 with `{"detail": "Sign in to continue"}`
- [x] 3.2 In `tests/test_api_ask.py`, override `get_current_user` in the `client` fixture
  with a stub returning an in-memory `User`, and add `TestAdmission`: without the override
  a post is 401 and `llm.calls` is empty; with a body carrying `user_id` the response is
  422; verify the whole file passes with no database
- [x] 3.3 In `evals/harness/run.py`, call `client.require_database()` and
  `client.register()` before the first case for every run (drop the chat-only condition)
  and adjust the printed line; update the endpoint paragraph in `evals/README.md`; verify
  `cd evals && uv run pytest -q` passes and `uv run harness/run.py --categories rag_basic
  --limit 2 --skip-judge` against a local service prints the registration line and two
  `ok` rows

## 4. Cross-origin policy

- [x] 4.1 In `create_app()`, add `CORSMiddleware(allow_origins=settings.allowed_origins or
  [], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])` before
  `RequestContextMiddleware` in code (so it runs inside it); verify `tests/test_app.py::
  TestCors`: with `allowed_origins=["https://app.example"]` a preflight `OPTIONS /api/chat`
  from that origin returns `access-control-allow-origin: https://app.example` and
  `access-control-allow-credentials: true` plus an `X-Request-ID`; from
  `https://evil.example` neither grant header is present; with the default empty list no
  grant header is present for any origin; a request with no `Origin` is unchanged

## 5. Local verification and docs

- [x] 5.1 Update `README.md`: Security paragraph (`/api/ask` requires a session; `/api/
  foods` and the auth routes remain public; rate limits and `ALLOWED_ORIGINS`; client
  address never logged), Configuration list, and the status line; verify `uv run ruff
  check . && uv run ruff format --check backend tests scripts && uv run pytest -q` are
  green with `docker compose up -d` running

## 6. Container image and start sequence

- [x] 6.1 Create `Dockerfile` (`python:3.14-slim`; `COPY --from=ghcr.io/astral-sh/uv:0.9
  /uv /usr/local/bin/uv`; `UV_COMPILE_BYTECODE=1`; `COPY pyproject.toml uv.lock` then
  `uv sync --frozen --no-dev --no-install-project`; `COPY backend alembic alembic.ini
  scripts knowledge-base nutrition-data`; non-root `app` user owning `/app` and `/data`;
  `ENV PATH=/app/.venv/bin:$PATH MILVUS_DB_PATH=/data/milvus.db`; `EXPOSE 8000`; `CMD
  ["scripts/start.sh"]`), `.dockerignore` (`.env*`, `milvus.db*`, `frontend/`,
  `node_modules/`, `evals/`, `.venv/`, `tests/`, `openspec/`, `.git/`, `*_Summary.md`),
  and executable `scripts/start.sh` (`set -euo pipefail`; `alembic upgrade head`; `python
  scripts/ingest.py`; `exec uvicorn backend.main:app --host 0.0.0.0 --port "${PORT:-8000}"
  --proxy-headers --forwarded-allow-ips="*" --no-access-log`); verify `docker build -t
  nutrition-api .` succeeds, `docker run --rm nutrition-api id -u` is not 0, and `docker
  run --rm nutrition-api sh -c 'ls -a /app'` shows no `.env`, `milvus.db`, `frontend`, or
  `tests`
- [x] 6.2 Run the image against the compose database: `docker run --rm -p 8001:8000
  --env-file .env -e DATABASE_URL=postgresql://nutrition:nutrition@host.docker.internal:
  5432/nutrition -e APP_ENV=prod -e LOG_FORMAT=json --add-host=host.docker.internal:
  host-gateway nutrition-api`; verify the log shows the migration at head, ingestion
  embedding 20 documents then a second start embedding 0 when `/data` is a mounted volume,
  `curl :8001/health` → `{"status":"ok","app_env":"prod","database":"reachable"}`, an
  unauthenticated `POST /api/ask` → 401, and starting with `-e SESSION_SECRET=` exits
  non-zero naming the setting

## 7. Deploy

- [ ] 7.1 Create `render.yaml`: one Docker web service (`healthCheckPath: /health`,
  `numInstances: 1`, `autoDeploy: true`, env `DATABASE_URL` from the database's
  `connectionString`, `APP_ENV=prod`, `LOG_FORMAT=json`, `SESSION_SECRET` with
  `generateValue: true`, `OPENROUTER_API_KEY` with `sync: false`, `ALLOWED_ORIGINS=`,
  `MILVUS_DB_PATH=/data/milvus.db`, optional disk at `/data`) and one PostgreSQL
  database; verify `render.yaml` parses (`python -c "import yaml,sys; yaml.safe_load(open
  ('render.yaml'))"`) and the Render blueprint import shows both resources
- [ ] 7.2 Deploy the backend from the blueprint, enter `OPENROUTER_API_KEY`; verify the
  deploy log shows migration + ingestion, `https://<service>.onrender.com/health` reports
  `database: reachable` and `app_env: prod`, unauthenticated `POST /api/ask` → 401, and
  the 31st `POST /api/chat` within a minute from one client → 429
- [ ] 7.3 Create the Vercel project on `frontend/` with `BACKEND_URL=https://<service>.
  onrender.com`; verify on the live URL: create account, save a child, ask a question that
  calls a tool and see `token` events arrive incrementally (not one burst), log a feed and
  see it after reload, sign out, and the `session` cookie shows `Secure; HttpOnly;
  SameSite=Lax` in devtools
- [ ] 7.4 Run the harness from outside: `EVAL_BASE_URL=https://<service>.onrender.com uv
  run harness/run.py --categories rag_basic --skip-judge`; verify it registers and every
  case passes its deterministic checks; add a "Deployment" section to `README.md` (live
  URLs, Render/Vercel settings, environment table, start sequence, rebuild-on-empty-disk
  note, rollback) and flip the status line; commit and push `main`

## 8. Continuous integration (cut line)

- [ ] 8.1 Create `.github/workflows/ci.yml` on push and pull request to `main`: a Python job
  (`astral-sh/setup-uv`, `uv sync --frozen`, `uv run ruff check .`, `uv run ruff format
  --check backend tests scripts`, `uv run pytest -q` with `TEST_DATABASE_URL` unset so `db`
  tests skip) and a frontend job (`pnpm/action-setup`, `pnpm install --frozen-lockfile`,
  `pnpm -C frontend lint && pnpm -C frontend typecheck && pnpm -C frontend test && pnpm -C
  frontend build`); verify the first run on `main` is green in the Actions tab
