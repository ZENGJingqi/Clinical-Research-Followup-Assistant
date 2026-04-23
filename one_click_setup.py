#!/usr/bin/env python3
"""
One-click setup for Clinical Research Followup Assistant.

Steps:
1) Create a virtual environment
2) Install dependencies
3) Generate a local `.env.local` file
4) Apply database migrations
5) Create the `root` account if needed
6) Ensure the `root` account has the Root role
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
MIN_PYTHON = (3, 11)


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


def ensure_supported_python() -> None:
    if sys.version_info < MIN_PYTHON:
        required = ".".join(str(part) for part in MIN_PYTHON)
        current = ".".join(str(part) for part in sys.version_info[:3])
        raise RuntimeError(
            f"Python {required}+ is required. Current interpreter: Python {current}."
        )


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
        raise RuntimeError(f"Virtual environment Python not found: {py}")
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
            raise RuntimeError(
                "Public mode requires --public-hosts, for example 1.2.3.4 or your.domain.com."
            )

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
        print(f"[OK] Created {ENV_LOCAL.name} without any AI API key.")
    else:
        print(f"[OK] Updated {ENV_LOCAL.name} and preserved the current AI configuration.")


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


def install_dependencies(py: Path, *, upgrade_pip: bool) -> None:
    if upgrade_pip:
        result = run([str(py), "-m", "pip", "install", "--upgrade", "pip"], check=False)
        if result.returncode != 0:
            print("[WARN] pip upgrade failed. Continuing with the bundled pip version.")
    run([str(py), "-m", "pip", "install", "-r", "requirements.txt"])


def main() -> int:
    parser = argparse.ArgumentParser(
        description="One-click setup for Clinical Research Followup Assistant."
    )
    parser.add_argument(
        "--mode",
        choices=["local", "public"],
        default="local",
        help="Deployment mode: local for loopback-only access, public for LAN/public access.",
    )
    parser.add_argument(
        "--public-hosts",
        default="",
        help="Comma-separated hostnames or IPs for public mode; written to FOLLOWUP_ALLOWED_HOSTS.",
    )
    parser.add_argument(
        "--public-origins",
        default="",
        help="Optional comma-separated CSRF trusted origins for public mode.",
    )
    parser.add_argument(
        "--upgrade-pip",
        action="store_true",
        help="Attempt to upgrade pip before installing dependencies.",
    )
    parser.add_argument(
        "--start",
        action="store_true",
        help="Start the development server immediately after setup.",
    )
    args = parser.parse_args()

    ensure_supported_python()

    deploy_mode = "public/LAN mode" if args.mode == "public" else "local-only mode"
    print(f"== Clinical Research Followup Assistant setup ({deploy_mode}) ==")

    py = ensure_venv()
    ensure_env_local(
        mode=args.mode,
        public_hosts=args.public_hosts,
        public_origins=args.public_origins,
    )

    install_dependencies(py, upgrade_pip=args.upgrade_pip)
    run([str(py), "manage.py", "migrate"])

    if not root_exists(py):
        print("\nFirst-time setup: please create the initial root account password.")
        run([str(py), "manage.py", "createsuperuser", "--username", "root"])
    else:
        print("\nThe root account already exists. Skipping account creation.")

    ensure_root_profile(py)

    print("\n[SUCCESS] Setup completed.")
    if args.mode == "public":
        print("Recommended bind address: 0.0.0.0:8000")
        print("Use the start_public_* script to launch the public/LAN mode.")
    else:
        print("Local URL: http://127.0.0.1:8000/")
        print(f"Start command: {start_command_hint()}")

    if args.start:
        bind = "0.0.0.0:8000" if args.mode == "public" else "127.0.0.1:8000"
        run([str(py), "manage.py", "runserver", bind], check=False)

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        raise SystemExit(1)
