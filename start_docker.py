#!/usr/bin/env python3
"""
Start SequelSpeak Docker containers (Robust Version + CLI Flags)
"""

import subprocess
import sys
import time
import shutil
import argparse
from pathlib import Path
from typing import List, Optional

# ===== Config =====
DOCKER_TIMEOUT = 60
HEALTH_CHECK_RETRIES = 10
HEALTH_CHECK_INTERVAL = 3
REQUIRED_ENV_KEYS = ["SECRET_KEY"]

# ===== Colors =====
GREEN = '\033[0;32m'
RED = '\033[0;31m'
YELLOW = '\033[1;33m'
BLUE = '\033[0;34m'
NC = '\033[0m'


def print_colored(msg: str, color: str = NC):
    print(f"{color}{msg}{NC}")


def run_command(
    cmd: List[str],
    check: bool = True,
    timeout: int = DOCKER_TIMEOUT
) -> Optional[subprocess.CompletedProcess]:
    """Run command safely with timeout + logging"""
    try:
        print_colored(f"$ {' '.join(cmd)}", BLUE)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        if check and result.returncode != 0:
            raise subprocess.CalledProcessError(
                result.returncode, cmd, result.stdout, result.stderr
            )
        return result
    except subprocess.TimeoutExpired:
        print_colored(f"✗ Command timed out: {' '.join(cmd)}", RED)
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print_colored(f"✗ Command failed: {' '.join(cmd)}", RED)
        print_colored(e.stderr.strip(), RED)
        if check:
            sys.exit(e.returncode)
        return None


def get_docker_compose_cmd() -> List[str]:
    """Detect docker compose vs docker-compose"""
    if shutil.which("docker-compose"):
        return ["docker-compose"]
    return ["docker", "compose"]


def check_docker():
    """Check Docker CLI + daemon"""
    if not shutil.which("docker"):
        print_colored("✗ Docker not installed", RED)
        sys.exit(1)

    result = run_command(["docker", "info"], check=False)
    if not result or result.returncode != 0:
        print_colored("✗ Docker daemon not running", RED)
        sys.exit(1)

    print_colored("✓ Docker is ready", GREEN)


def ensure_env():
    """Ensure .env exists + validate keys"""
    env_file = Path(".env")
    example = Path(".env.example")

    if not env_file.exists():
        if example.exists():
            shutil.copy(example, env_file)
            print_colored("✓ Created .env from template", GREEN)
        else:
            print_colored("✗ Missing .env and .env.example", RED)
            sys.exit(1)

    # Validate required keys
    content = env_file.read_text()
    missing = [k for k in REQUIRED_ENV_KEYS if k not in content]

    if missing:
        print_colored(f"⚠ Missing env keys: {missing}", YELLOW)


def build_frontend(compose_cmd: List[str]):
    print_colored("→ Building frontend (no cache)...", YELLOW)
    run_command([
        *compose_cmd,
        "--env-file", ".env",
        "build", "--no-cache", "frontend"
    ])


def start_services(compose_cmd: List[str], skip_migrations: bool):
    print_colored("→ Starting services...", YELLOW)

    services = ["backend", "frontend", "redis", "db"]

    if not skip_migrations:
        services.append("migrate")

    run_command([
        *compose_cmd,
        "--env-file", ".env",
        "up", "-d", "--build",
        *services
    ])


def run_migrations(compose_cmd: List[str]):
    """Run DB migrations inside backend container"""
    print_colored("→ Running database migrations...", YELLOW)

    result = run_command([
        *compose_cmd,
        "exec",
        "backend",
        "alembic",
        "upgrade",
        "head"
    ], check=False)

    if not result or result.returncode != 0:
        print_colored("✗ Migration failed", RED)
        sys.exit(1)

    print_colored("✓ Migrations completed", GREEN)


def wait_for_services(compose_cmd: List[str]):
    """Wait until containers are running"""
    print_colored("Waiting for services to stabilize...", BLUE)

    for attempt in range(HEALTH_CHECK_RETRIES):
        result = run_command([*compose_cmd, "ps"], check=False)

        if result and "Up" in result.stdout:
            print_colored("✓ Services are up", GREEN)
            return

        print_colored(f"Retry {attempt+1}/{HEALTH_CHECK_RETRIES}...", YELLOW)
        time.sleep(HEALTH_CHECK_INTERVAL)

    print_colored("⚠ Services may not be fully healthy", YELLOW)


def show_status(compose_cmd: List[str]):
    result = run_command([*compose_cmd, "ps"], check=False)
    print_colored("\nService Status:", BLUE)
    print(result.stdout if result else "")


def parse_args():
    parser = argparse.ArgumentParser(description="Start SequelSpeak services")
    parser.add_argument(
        "--skip-migrations",
        action="store_true",
        help="Skip running database migrations"
    )
    return parser.parse_args()


def main():
    args = parse_args()
    compose_cmd = get_docker_compose_cmd()

    print_colored("=" * 60, BLUE)
    print_colored("Starting SequelSpeak (Robust Mode)", BLUE)
    print_colored("=" * 60, BLUE)

    # 1. Docker check
    print_colored("\n[1/5] Docker Check", BLUE)
    check_docker()

    # 2. Env check
    print_colored("\n[2/5] Environment Setup", BLUE)
    ensure_env()

    # 3. Build + Start
    print_colored("\n[3/5] Build & Start", BLUE)
    build_frontend(compose_cmd)
    start_services(compose_cmd, args.skip_migrations)

    # 4. Migrations (optional)
    print_colored("\n[4/5] Database Setup", BLUE)
    if args.skip_migrations:
        print_colored("⚠ Skipping migrations (flag enabled)", YELLOW)
    else:
        run_migrations(compose_cmd)

    # 5. Health check
    print_colored("\n[5/5] Health Check", BLUE)
    wait_for_services(compose_cmd)

    show_status(compose_cmd)

    print_colored("\n✓ SequelSpeak is running!", GREEN)
    print_colored("Frontend:  http://localhost", GREEN)
    print_colored("Backend:   http://localhost:8000", GREEN)
    print_colored("Docs:      http://localhost:8000/docs", GREEN)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print_colored("\n✗ Interrupted by user", YELLOW)
        sys.exit(130)