#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [[ ! -x ".venv/bin/python" ]]; then
  echo "未检测到虚拟环境，请先执行: bash setup_public_linux.sh"
  exit 1
fi

exec .venv/bin/gunicorn config.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers 2 \
  --timeout 120

