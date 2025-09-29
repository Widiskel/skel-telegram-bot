#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$ROOT_DIR/venv"

find_python() {
  local candidates=()
  if [[ -n "${PYTHON_BIN:-}" ]]; then
    candidates+=("$PYTHON_BIN")
  fi
  candidates+=("$HOME/.pyenv/versions/3.12.0/bin/python" "python3.12" "python3")
  for candidate in "${candidates[@]}"; do
    if [[ -x "$candidate" ]]; then
      echo "$candidate"
      return 0
    fi
  done
  echo "Error: Python 3.12 interpreter not found. Install Python 3.12 or set PYTHON_BIN." >&2
  exit 1
}

PYTHON_BIN=$(find_python)

if [[ ! -d "$VENV_DIR" ]]; then
  echo "[setup] Creating virtualenv in $VENV_DIR"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
else
  echo "[setup] Using existing virtualenv in $VENV_DIR"
fi

"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install -r "$ROOT_DIR/requirements.txt"

echo "\nSetup complete. Activate via 'source venv/bin/activate' and run ./start.sh"
