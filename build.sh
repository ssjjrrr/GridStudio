#!/bin/sh
# Native Linux/macOS build. PYTHON may select a Python 3.12.14 interpreter.
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
if [ ! -x .venv/bin/python ]; then
    "${PYTHON:-python3}" -m venv .venv
fi
.venv/bin/python -m pip install -r requirements.txt pyinstaller==6.20.0
exec .venv/bin/python scripts/build.py "$@"
