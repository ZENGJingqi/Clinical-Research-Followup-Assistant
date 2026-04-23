#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [[ ! -x ".venv/bin/python" ]]; then
  echo "未检测到虚拟环境，请先执行: bash setup_linux.sh"
  exit 1
fi

exec .venv/bin/python manage.py runserver 127.0.0.1:8000
