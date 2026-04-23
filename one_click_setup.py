#!/usr/bin/env python3
"""
解压后本地一键部署脚本：
1) 创建虚拟环境
2) 安装依赖
3) 生成本地 .env.local（不含任何 API 密钥）
4) 数据库迁移
5) 交互创建 root 账号（密码由使用者自行设置）
6) 绑定 Root 角色

默认仅本机访问（127.0.0.1 / localhost）。
"""

from __future__ import annotations

import argparse
import os
import secrets
import subprocess
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
VENV_DIR = BASE_DIR / ".venv"
ENV_LOCAL = BASE_DIR / ".env.local"


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    print(f"[RUN] {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=str(BASE_DIR), check=check)


def run_capture(cmd: list[str]) -> str:
    print(f"[RUN] {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        cwd=str(BASE_DIR),
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return result.stdout


def get_venv_python() -> Path:
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def start_command_hint() -> str:
    if os.name == "nt":
        return r".\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000"
    return "./.venv/bin/python manage.py runserver 127.0.0.1:8000"


def parse_env_file(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip()
    return data


def write_env_file(path: Path, data: dict[str, str]) -> None:
    lines = [f"{key}={value}" for key, value in data.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def split_csv(text: str) -> list[str]:
    return [item.strip() for item in text.split(",") if item.strip()]


def normalize_allowed_host(host: str) -> str:
    value = host.strip()
    if value.startswith("http://"):
        value = value[len("http://") :]
    elif value.startswith("https://"):
        value = value[len("https://") :]
    if "/" in value:
        value = value.split("/", 1)[0]
    # 常见输入: example.com:8000 -> example.com
    if ":" in value and value.count(":") == 1:
        left, right = value.rsplit(":", 1)
        if right.isdigit():
            value = left
    return value.strip()


def derive_csrf_origins(hosts: list[str]) -> list[str]:
    origins: list[str] = []
    for host in hosts:
        if host in {"*", "127.0.0.1", "localhost"}:
            continue
        if host.startswith("http://") or host.startswith("https://"):
            origins.append(host)
            continue
        origins.append(f"http://{host}")
        origins.append(f"https://{host}")
    # 保持顺序去重
    seen: set[str] = set()
    deduped: list[str] = []
    for item in origins:
        if item not in seen:
            seen.add(item)
            deduped.append(item)
    return deduped


def ensure_venv() -> Path:
    if not VENV_DIR.exists():
        run([sys.executable, "-m", "venv", str(VENV_DIR)])
    py = get_venv_python()
    if not py.exists():
        raise RuntimeError(f"虚拟环境 Python 不存在: {py}")
    return py


def ensure_env_local(
    *,
    mode: str,
    public_hosts: str | None,
    public_origins: str | None,
) -> None:
    current = parse_env_file(ENV_LOCAL)
    created = not ENV_LOCAL.exists()

    if "FOLLOWUP_SECRET_KEY" not in current:
        current["FOLLOWUP_SECRET_KEY"] = secrets.token_urlsafe(48)
    current["FOLLOWUP_DEBUG"] = "false"

    if mode == "public":
        hosts = [normalize_allowed_host(item) for item in split_csv(public_hosts or "")]
        hosts = [item for item in hosts if item]
        if not hosts:
            raise RuntimeError("公网部署必须提供 --public-hosts，例如 1.2.3.4 或 your.domain.com")
        # 公网模式也保留本机回环访问，便于运维本地测试。
        merged_hosts = []
        for host in [*hosts, "127.0.0.1", "localhost"]:
            if host not in merged_hosts:
                merged_hosts.append(host)
        current["FOLLOWUP_ALLOWED_HOSTS"] = ",".join(merged_hosts)

        if public_origins and split_csv(public_origins):
            origins = split_csv(public_origins)
        else:
            origins = derive_csrf_origins(hosts)
        current["FOLLOWUP_CSRF_TRUSTED_ORIGINS"] = ",".join(origins)
    else:
        current["FOLLOWUP_ALLOWED_HOSTS"] = "127.0.0.1,localhost"
        current["FOLLOWUP_CSRF_TRUSTED_ORIGINS"] = ""

    current.setdefault("AI_PROVIDER", "aliyun")
    current.setdefault("AI_API_KEY", "")
    current.setdefault("AI_MODEL", "qwen-plus")
    current.setdefault(
        "AI_BASE_URL",
        "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
    )
    write_env_file(ENV_LOCAL, current)

    if created:
        print(f"[OK] 已生成 {ENV_LOCAL.name}（未写入任何 API 密钥）")
    else:
        print(f"[OK] 已更新 {ENV_LOCAL.name}（保留现有 AI 密钥等配置）")


def root_exists(py: Path) -> bool:
    output = run_capture(
        [
            str(py),
            "manage.py",
            "shell",
            "-c",
            "from django.contrib.auth.models import User; print('YES' if User.objects.filter(username='root').exists() else 'NO')",
        ]
    )
    return "YES" in output


def ensure_root_profile(py: Path) -> None:
    run(
        [
            str(py),
            "manage.py",
            "shell",
            "-c",
            (
                "from django.contrib.auth.models import User; "
                "from followup.models import UserProfile; "
                "u=User.objects.get(username='root'); "
                "UserProfile.objects.update_or_create(user=u, defaults={'role': UserProfile.ROLE_ROOT})"
            ),
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="临床科研智能随访助手本地一键部署")
    parser.add_argument(
        "--mode",
        choices=["local", "public"],
        default="local",
        help="部署模式：local=仅本机访问；public=公网/局域网访问",
    )
    parser.add_argument(
        "--public-hosts",
        default="",
        help="仅 public 模式使用。逗号分隔的域名/IP（写入 FOLLOWUP_ALLOWED_HOSTS）",
    )
    parser.add_argument(
        "--public-origins",
        default="",
        help="仅 public 模式使用。逗号分隔的 CSRF origins（可留空自动推导）",
    )
    parser.add_argument(
        "--start",
        action="store_true",
        help="部署完成后直接启动服务",
    )
    args = parser.parse_args()

    deploy_mode = "公网/局域网访问模式" if args.mode == "public" else "仅本机访问模式"
    print(f"== 临床科研智能随访助手 一键部署（{deploy_mode}）==")
    py = ensure_venv()
    ensure_env_local(
        mode=args.mode,
        public_hosts=args.public_hosts,
        public_origins=args.public_origins,
    )

    run([str(py), "-m", "pip", "install", "--upgrade", "pip"])
    run([str(py), "-m", "pip", "install", "-r", "requirements.txt"])
    run([str(py), "manage.py", "migrate"])

    if not root_exists(py):
        print("\n首次部署：请按提示设置初始 root 账号密码。")
        run([str(py), "manage.py", "createsuperuser", "--username", "root"])
    else:
        print("\n已存在 root 账号，跳过创建。")

    ensure_root_profile(py)

    print("\n[SUCCESS] 部署完成。")
    if args.mode == "public":
        print("服务监听建议: 0.0.0.0:8000")
        print("请使用 start_public_* 脚本启动公网模式。")
    else:
        print("本机访问地址: http://127.0.0.1:8000/")
        print(f"启动命令: {start_command_hint()}")

    if args.start:
        bind = "0.0.0.0:8000" if args.mode == "public" else "127.0.0.1:8000"
        run([str(py), "manage.py", "runserver", bind], check=False)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
