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
    """Check if .env.docker file exists"""
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
            return True
        else:
            print_colored("✗ .env.example not found", RED)
            return False
    return True


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
    
    # Step 1: Build frontend with no cache to ensure fresh env vars
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
    
    # Step 2: Build other services (can use cache) and start all
    print_colored("  → Building remaining services and starting...", YELLOW)
    result = run_command([
        'docker', 'compose',
        '--env-file', '.env.docker',
        'up', '-d', '--build'
    ], check=False)
    
    if result.returncode != 0:
        print_colored("✗ Failed to start containers", RED)
        print_colored(result.stderr, RED)
        sys.exit(1)
    
    print()
    print_colored("✓ Containers started successfully", GREEN)
    print()
    
    # Wait for services to be healthy
    print_colored("[4/4] Waiting for services to be healthy...", BLUE)
    time.sleep(5)
    
    # Check service status
    result = run_command(['docker', 'compose', 'ps'], check=False)
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
    print_colored(f"  Frontend:  {GREEN}http://localhost{NC}")
    print_colored(f"  Backend:   {GREEN}http://localhost:8000{NC}")
    print_colored(f"  API Docs:  {GREEN}http://localhost:8000/docs{NC}")
    print()
    print_colored("Useful Commands:", BLUE)
    print_colored(f"  View logs:        {YELLOW}docker compose logs -f{NC}")
    print_colored(f"  Stop containers:  {YELLOW}python3 stop_docker.py{NC}")
    print_colored(f"  Restart:          {YELLOW}python3 start_docker.py{NC}")
    print()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print()
        print_colored("✗ Cancelled by user", YELLOW)
        sys.exit(1)
