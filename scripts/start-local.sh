#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# Node.js must be installed and available on PATH.
if [ ! -x .venv/bin/python ] || ! command -v node >/dev/null; then
  echo 'Install the dependencies using README.md first.'; exit 1
fi
if [ ! -d frontend/dist ]; then
  node frontend/node_modules/typescript/bin/tsc --noEmit -p frontend/tsconfig.json
  node frontend/node_modules/vite/bin/vite.js build frontend
fi
children=()
cleanup() { for child in "${children[@]}"; do kill "$child" 2>/dev/null || true; done; }
trap cleanup EXIT INT TERM
if ! .venv/bin/python -c 'from backend.db import connection; c=connection(); c.__enter__().execute("SELECT 1")' 2>/dev/null; then
  node scripts/local-db.mjs & children+=("$!")
  for _ in {1..30}; do
    if .venv/bin/python -c 'from backend.db import connection; c=connection(); c.__enter__().execute("SELECT 1")' 2>/dev/null; then break; fi
    sleep 1
  done
fi
.venv/bin/python -m backend.db
.venv/bin/uvicorn backend.app:app --host 127.0.0.1 --port 8000 & children+=("$!")
.venv/bin/python -m backend.worker & children+=("$!")
echo 'Stockroom: http://127.0.0.1:8000 · Ctrl+C stops processes started by this script.'
wait
