#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 was not found. Please install Python 3.11+ first."
  exit 1
fi

python3 one_click_setup.py --mode local
