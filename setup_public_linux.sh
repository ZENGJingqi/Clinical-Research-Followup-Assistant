#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 was not found. Please install Python 3.11+ first."
  exit 1
fi

read -rp "Enter public host or IP (comma-separated if multiple): " PUBLIC_HOSTS
if [[ -z "${PUBLIC_HOSTS// }" ]]; then
  echo "No public host or IP was provided. Setup cancelled."
  exit 1
fi

python3 one_click_setup.py --mode public --public-hosts "$PUBLIC_HOSTS"
echo "[SUCCESS] Public/LAN setup completed."
echo "Make sure port 8000 is allowed by your firewall or cloud security group."
