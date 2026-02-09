#!/usr/bin/env python3
"""
Stop SequelSpeak Docker containers
Stops and optionally removes all containers and volumes
"""

import subprocess
import sys
import argparse

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


def check_docker_running() -> bool:
    """Check if Docker daemon is running"""
    try:
        result = run_command(['docker', 'info'], check=False)
        return result.returncode == 0
    except FileNotFoundError:
        return False


def get_running_containers() -> list[str]:
    """Get list of running SequelSpeak containers"""
    result = run_command(
        ['docker', 'compose', 'ps', '-q'],
        check=False
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip().split('\n')
    return []


def main():
    """Main function to stop Docker containers"""
    parser = argparse.ArgumentParser(
        description='Stop SequelSpeak Docker containers',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  python3 stop_docker.py              # Stop containers (keep volumes)
  python3 stop_docker.py --volumes    # Stop containers and remove volumes
  python3 stop_docker.py --clean      # Stop, remove containers, volumes, and images
        '''
    )
    parser.add_argument(
        '-v', '--volumes',
        action='store_true',
        help='Remove volumes (deletes Redis data)'
    )
    parser.add_argument(
        '--clean',
        action='store_true',
        help='Remove everything (containers, volumes, and images)'
    )
    
    args = parser.parse_args()
    
    print_colored("=" * 60, BLUE)
    print_colored("Stopping SequelSpeak Docker Containers", BLUE)
    print_colored("=" * 60, BLUE)
    print()
    
    # Check Docker
    if not check_docker_running():
        print_colored("✗ Docker is not running", RED)
        sys.exit(1)
    
    # Check if containers are running
    containers = get_running_containers()
    if not containers:
        print_colored("ℹ No SequelSpeak containers are currently running", YELLOW)
        
        # Still try to clean up if --clean flag is used
        if args.clean:
            print()
            print_colored("Cleaning up images...", BLUE)
            run_command(['docker', 'compose', 'down', '--rmi', 'all'], check=False)
            print_colored("✓ Cleanup complete", GREEN)
        
        return
    
    print_colored(f"Found {len(containers)} running container(s)", BLUE)
    print()
    
    # Build docker compose down command
    cmd = ['docker', 'compose', 'down']
    
    if args.clean:
        print_colored("⚠️  Warning: This will remove containers, volumes, AND images", YELLOW)
        response = input("Are you sure? (yes/no): ").strip().lower()
        if response != 'yes':
            print_colored("✗ Cancelled by user", YELLOW)
            sys.exit(0)
        cmd.extend(['--volumes', '--rmi', 'all'])
    elif args.volumes:
        print_colored("⚠️  Warning: This will delete Redis data", YELLOW)
        response = input("Are you sure? (yes/no): ").strip().lower()
        if response != 'yes':
            print_colored("✗ Cancelled by user", YELLOW)
            sys.exit(0)
        cmd.append('--volumes')
    
    # Stop containers
    print_colored("Stopping containers...", BLUE)
    result = run_command(cmd, check=False)
    
    if result.returncode != 0:
        print_colored("✗ Failed to stop containers", RED)
        print_colored(result.stderr, RED)
        sys.exit(1)
    
    print()
    print_colored("=" * 60, GREEN)
    print_colored("✓ Containers stopped successfully", GREEN)
    print_colored("=" * 60, GREEN)
    print()
    
    if args.clean:
        print_colored("Removed:", BLUE)
        print_colored("  ✓ Containers", GREEN)
        print_colored("  ✓ Volumes (Redis data)", GREEN)
        print_colored("  ✓ Images", GREEN)
        print()
        print_colored("To start fresh: python3 start_docker.py", YELLOW)
    elif args.volumes:
        print_colored("Removed:", BLUE)
        print_colored("  ✓ Containers", GREEN)
        print_colored("  ✓ Volumes (Redis data)", GREEN)
        print()
        print_colored("To restart: python3 start_docker.py", YELLOW)
    else:
        print_colored("Containers stopped (volumes preserved)", BLUE)
        print_colored("To restart: python3 start_docker.py", YELLOW)
    print()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print()
        print_colored("✗ Cancelled by user", YELLOW)
        sys.exit(1)
