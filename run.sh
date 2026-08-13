#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

if [ ! -d ".venv" ]; then
  echo "Creating virtual environment..."
  PYTHON_BIN="$(command -v python3.12 || echo /opt/homebrew/bin/python3.12)"
  "$PYTHON_BIN" -m venv .venv
fi

source .venv/bin/activate

if [ ! -f ".venv/.deps-installed" ]; then
  echo "Installing dependencies (first run only, this can take a few minutes)..."
  pip install --upgrade pip --quiet
  pip install -r backend/requirements.txt --quiet
  python -m spacy download en_core_web_lg --quiet
  touch .venv/.deps-installed
fi

echo "Starting The REDACTOR at http://127.0.0.1:8420"
( sleep 1.5 && open "http://127.0.0.1:8420" ) &

cd backend
exec uvicorn app.main:app --host 127.0.0.1 --port 8420
