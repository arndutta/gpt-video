#!/usr/bin/env bash
set -eu
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  echo "Missing .venv. Follow the setup steps in README.md." >&2
  exit 1
fi
exec .venv/bin/python -m scripts.launch "$@"
