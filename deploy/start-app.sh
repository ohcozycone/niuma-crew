#!/bin/sh
set -eu
umask 077
# Explicit deployment migration; the ASGI application itself never upgrades tables.
alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port 3000 --no-proxy-headers --no-access-log
