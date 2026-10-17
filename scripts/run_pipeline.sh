#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -f ".venv/Scripts/python.exe" ] && [ ! -f ".venv/bin/python" ]; then
  echo "未找到 .venv，请先运行 scripts/setup_env.py" >&2
  exit 1
fi
if [ -f ".venv/Scripts/python.exe" ]; then
  PY=".venv/Scripts/python.exe"
else
  PY=".venv/bin/python"
fi
"$PY" -m src.etl.pipeline "$@"
