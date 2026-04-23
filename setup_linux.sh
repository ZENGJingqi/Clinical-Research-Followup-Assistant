#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "未检测到 python3，请先安装 Python 3.11+。"
  exit 1
fi

python3 one_click_setup.py --mode local
