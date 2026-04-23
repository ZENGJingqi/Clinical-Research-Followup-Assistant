#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "未检测到 python3，请先安装 Python 3.11+。"
  exit 1
fi

read -rp "请输入公网访问域名或IP（多个用逗号分隔）: " PUBLIC_HOSTS
if [[ -z "${PUBLIC_HOSTS// }" ]]; then
  echo "未输入公网域名/IP，已取消。"
  exit 1
fi

python3 one_click_setup.py --mode public --public-hosts "$PUBLIC_HOSTS"
echo "[SUCCESS] 全网部署完成。"
echo "请确认 8000 端口已在系统防火墙/安全组放行。"
