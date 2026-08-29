#!/bin/sh
# Container start sequence (production-hardening spec): bring the schema to head, make
# sure the knowledge base is embedded, then serve. Either preparatory step failing stops
# the container before it serves a single request.
#
# The virtualenv uv built is on PATH (Dockerfile), so the binaries are called directly.
set -eu

echo "start: applying schema migrations"
alembic upgrade head

# Re-runnable: embeds only documents that are new or changed. On an empty /data this is
# the whole corpus (seconds); with a mounted disk it is nothing.
echo "start: ingesting the knowledge base into ${MILVUS_DB_PATH:-milvus.db}"
python scripts/ingest.py

# --proxy-headers / --forwarded-allow-ips="*": the only peer that can reach this
# container is the hosting proxy, so its X-Forwarded-For is the real client address the
# rate limiter keys on. --no-access-log: the application writes its own access record.
echo "start: serving on port ${PORT:-8000}"
exec uvicorn backend.main:app \
    --host 0.0.0.0 \
    --port "${PORT:-8000}" \
    --proxy-headers \
    --forwarded-allow-ips="*" \
    --no-access-log
