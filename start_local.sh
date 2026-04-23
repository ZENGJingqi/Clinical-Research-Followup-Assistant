#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [[ ! -x ".venv/bin/python" ]]; then
  echo "Virtual environment not found. Run 'bash setup_linux.sh' first."
  exit 1
fi

exec .venv/bin/python manage.py runserver 127.0.0.1:8000
