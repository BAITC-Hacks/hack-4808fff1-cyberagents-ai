#!/usr/bin/env bash
set -euo pipefail
if [ -x .venv/bin/python ]; then
  exec .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
else
  exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
fi
