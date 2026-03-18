#!/usr/bin/env python3
"""
Start SequelSpeak Docker containers
Builds images if needed and starts all services (backend, frontend, redis)
"""

import subprocess
import sys
import time
from pathlib import Path

# Color codes for output
GREEN = '\033[0;32m'
RED = '\033[0;31m'
YELLOW = '\033[1;33m'
BLUE = '\033[0;34m'
NC = '\033[0m'  # No Color


def print_colored(message: str, color: str = NC) -> None:
    """Print colored message to stdout"""
    print(f"{color}{message}{NC}")


def run_command(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """Run a shell command and return the result"""
    try:
        result = subprocess.run(
            cmd,
            check=check,
            capture_output=True,
            text=True
        )
        return result
    except subprocess.CalledProcessError as e:
        print_colored(f"Error running command: {' '.join(cmd)}", RED)
        print_colored(f"Error: {e.stderr}", RED)
        if check:
            sys.exit(1)
        return e


def check_docker_installed() -> bool:
    """Check if Docker is installed and running"""
    try:
        result = run_command(['docker', '--version'], check=False)
        if result.returncode != 0:
            return False
        
        # Check if Docker daemon is running
        result = run_command(['docker', 'info'], check=False)
        return result.returncode == 0
    except FileNotFoundError:
        return False


def check_env_file() -> bool:
    """Check if .env.docker file exists and contains required variables"""
    env_file = Path('.env.docker')
    if not env_file.exists():
        print_colored("⚠️  Warning: .env.docker not found", YELLOW)
        print_colored("Creating .env.docker from template...", YELLOW)

        example_file = Path('.env.docker.example')
        if example_file.exists():
            import shutil
            shutil.copy(example_file, env_file)
            print_colored("✓ Created .env.docker from .env.docker.example", GREEN)
            print_colored("\n⚠️  IMPORTANT: Edit .env.docker and set:", YELLOW)
            print_colored("  - SECRET_KEY (generate with: openssl rand -hex 32)", YELLOW)
            print_colored("  - CLERK_SECRET_KEY (from Clerk Dashboard)", YELLOW)
            print_colored("  - CLERK_PUBLISHABLE_KEY (from Clerk Dashboard)", YELLOW)
            print_colored("  - POSTGRES_USER (internal DB username, e.g. postgres)", YELLOW)
            print_colored("  - POSTGRES_PASSWORD (internal DB password)", YELLOW)
            return True
        else:
            print_colored("✗ .env.docker.example not found", RED)
            return False

    # Warn if postgres credentials are missing (needed for INTERNAL_DATABASE_URL interpolation)
    content = env_file.read_text()
    missing = [v for v in ('POSTGRES_USER', 'POSTGRES_PASSWORD') if v not in content]
    if missing:
        print_colored(f"⚠️  Warning: .env.docker is missing: {', '.join(missing)}", YELLOW)
        print_colored("  These are required for the internal PostgreSQL service.", YELLOW)
        print_colored("  Add them to .env.docker, e.g.:", YELLOW)
        for var in missing:
            default = 'postgres'
            print_colored(f"    {var}={default}", YELLOW)

    return True


def _wait_for_migration(timeout: int = 120) -> bool:
    """
    Poll until the 'migrate' container exits with code 0 (migrations applied)
    or timeout expires.  Returns True on success, False on failure/timeout.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = run_command(
            ['docker', 'compose', '--env-file', '.env.docker',
             'ps', '-a', '--format', '{{.Service}}\t{{.State}}\t{{.ExitCode}}'],
            check=False
        )
        for line in result.stdout.splitlines():
            parts = line.split('\t')
            if len(parts) >= 3 and parts[0].strip() == 'migrate':
                state, exit_code = parts[1].strip(), parts[2].strip()
                if state == 'exited' and exit_code == '0':
                    return True
                if state == 'exited' and exit_code != '0':
                    return False  # migration failed
                # still running — keep waiting
                break
        time.sleep(3)
    return False  # timed out


def main():
    """Main function to start Docker containers"""
    print_colored("=" * 60, BLUE)
    print_colored("Starting SequelSpeak Docker Containers", BLUE)
    print_colored("=" * 60, BLUE)
    print()
    
    # Check Docker installation
    print_colored("[1/4] Checking Docker installation...", BLUE)
    if not check_docker_installed():
        print_colored("✗ Docker is not installed or not running", RED)
        print_colored("\nPlease install Docker Desktop:", YELLOW)
        print_colored("  macOS: https://docs.docker.com/desktop/install/mac-install/", YELLOW)
        print_colored("  Linux: https://docs.docker.com/engine/install/", YELLOW)
        sys.exit(1)
    print_colored("✓ Docker is installed and running", GREEN)
    print()
    
    # Check environment file
    print_colored("[2/4] Checking environment configuration...", BLUE)
    check_env_file()
    print()
    
    # Build and start containers
    print_colored("[3/4] Building and starting containers...", BLUE)
    print_colored("This may take a few minutes on first run...", YELLOW)
    print()

    # Step 1: Build backend and migrate services (can use cache)
    print_colored("  → Building backend services...", YELLOW)
    backend_build = run_command([
        'docker', 'compose',
        '--env-file', '.env.docker',
        'build', 'backend', 'migrate'
    ], check=False)

    if backend_build.returncode != 0:
        print_colored("✗ Failed to build backend/migrate services", RED)
        print_colored(backend_build.stderr, RED)
        sys.exit(1)

    print_colored("  ✓ Backend services built successfully", GREEN)
    print()

    # Step 2: Build frontend with no cache to pick up fresh env vars
    print_colored("  → Building frontend (no cache for fresh env vars)...", YELLOW)
    frontend_build = run_command([
        'docker', 'compose',
        '--env-file', '.env.docker',
        'build', '--no-cache', 'frontend'
    ], check=False)

    if frontend_build.returncode != 0:
        print_colored("✗ Failed to build frontend", RED)
        print_colored(frontend_build.stderr, RED)
        sys.exit(1)

    print_colored("  ✓ Frontend built successfully", GREEN)
    print()

    # Step 3: Start all services (images already built, so --no-build avoids redundant rebuilds)
    print_colored("  → Starting all services...", YELLOW)
    result = run_command([
        'docker', 'compose',
        '--env-file', '.env.docker',
        'up', '-d', '--no-build'
    ], check=False)

    if result.returncode != 0:
        print_colored("✗ Failed to start containers", RED)
        print_colored(result.stderr, RED)
        sys.exit(1)

    print()
    print_colored("✓ Containers started successfully", GREEN)
    print()

    # Wait for services to become healthy, including Alembic migration
    print_colored("[4/4] Waiting for services to be healthy...", BLUE)

    print_colored("  → Waiting for database and migrations...", YELLOW)
    migrate_ok = _wait_for_migration(timeout=120)
    if not migrate_ok:
        print_colored("✗ Database migration did not complete in time", RED)
        print_colored("  Check logs with: docker compose logs migrate", YELLOW)
        sys.exit(1)
    print_colored("  ✓ Database migrations applied", GREEN)

    # Brief pause for backend to finish its startup after migrations
    time.sleep(5)

    # Check service status
    result = run_command(['docker', 'compose', '--env-file', '.env.docker', 'ps'], check=False)
    print()
    print_colored("Service Status:", BLUE)
    print_colored("-" * 60, BLUE)
    print(result.stdout)

    # Display access information
    print_colored("=" * 60, GREEN)
    print_colored("✓ SequelSpeak is running!", GREEN)
    print_colored("=" * 60, GREEN)
    print()
    print_colored("Access URLs:", BLUE)
    print_colored(f"  Frontend:    {GREEN}http://localhost{NC}")
    print_colored(f"  Backend:     {GREEN}http://localhost:8000{NC}")
    print_colored(f"  API Docs:    {GREEN}http://localhost:8000/docs{NC}")
    print_colored(f"  PostgreSQL:  {GREEN}localhost:5433{NC}  (internal DB, user: postgres)")
    print_colored(f"  Redis:       {GREEN}localhost:6379{NC}")
    print()
    print_colored("Useful Commands:", BLUE)
    print_colored(f"  View logs (all):      {YELLOW}docker compose logs -f{NC}")
    print_colored(f"  View backend logs:    {YELLOW}docker compose logs -f backend{NC}")
    print_colored(f"  View migration logs:  {YELLOW}docker compose logs migrate{NC}")
    print_colored(f"  Stop containers:      {YELLOW}python3 stop_docker.py{NC}")
    print_colored(f"  Restart:              {YELLOW}python3 start_docker.py{NC}")
    print()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print()
        print_colored("✗ Cancelled by user", YELLOW)
        sys.exit(1)
