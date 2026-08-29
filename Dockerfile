# FastAPI application image (Day 7, production-hardening spec). The frontend is built by
# Vercel and the database is managed; this image is the API only.
#
#   docker build -t nutrition-api .
#   docker run --rm -p 8000:8000 --env-file .env nutrition-api
#
# Start sequence (scripts/start.sh): alembic upgrade head -> scripts/ingest.py -> uvicorn.
FROM python:3.14-slim

# uv only installs the dependencies; the runtime image never calls it (design Decision 6).
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    # Milvus Lite lives here; mount a disk at /data to keep it across deploys, otherwise
    # the start script rebuilds it from the corpus.
    MILVUS_DB_PATH=/data/milvus.db

WORKDIR /app

# Dependencies first, from the committed lockfile only, so source edits reuse this layer.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# `backend` is imported from the working directory, as it is on the host (no install).
COPY backend ./backend
COPY alembic ./alembic
COPY alembic.ini ./
COPY scripts/ingest.py scripts/start.sh ./scripts/
COPY knowledge-base ./knowledge-base
COPY nutrition-data ./nutrition-data

RUN groupadd --system app && useradd --system --gid app --home /app app \
    && mkdir -p /data \
    && chown -R app:app /app /data \
    && chmod +x scripts/start.sh
USER app

EXPOSE 8000

# uvicorn's --proxy-headers / --forwarded-allow-ips="*" in start.sh trust the hosting
# proxy for the client address; never run this image directly on a public interface.
CMD ["scripts/start.sh"]
