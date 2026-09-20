#!/bin/sh
set -e

alembic upgrade head

exec uvicorn app.api.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --proxy-headers \
  --forwarded-allow-ips '*'
