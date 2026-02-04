#!/usr/bin/env python3
"""
Demo script to showcase timestamp tracking in ConnectionHealthMonitor.

This script demonstrates the new timestamp tracking capabilities added to solve Issue #3.1:
- Track when health checks are performed
- Determine when the database went down
- Calculate downtime duration
- Track time since last successful connection

Run this script to see the timestamp tracking in action:
    python scripts/demo_timestamp_tracking.py
"""

import asyncio
import time
from datetime import datetime
from utils.connection_resilience import ConnectionHealthMonitor


def format_timestamp(ts: float | None) -> str:
    """Format Unix timestamp to human-readable string."""
    if ts is None:
        return "Never"
    return datetime.fromtimestamp(ts).strftime("%H:%M:%S.%f")[:-3]


def format_duration(duration: float | None) -> str:
    """Format duration in seconds to human-readable string."""
    if duration is None:
        return "N/A"
    return f"{duration:.3f}s"


async def print_status(monitor: ConnectionHealthMonitor, label: str):
    """Print current health monitor status."""
    state = await monitor.get_state()
    consecutive_failures = await monitor.get_consecutive_failures()
    last_check = await monitor.get_last_check_time()
    last_healthy = await monitor.get_last_healthy_time()
    first_failure = await monitor.get_first_failure_time()
    downtime = await monitor.get_downtime_duration()
    time_since_check = await monitor.get_time_since_last_check()
    time_since_healthy = await monitor.get_time_since_last_healthy()
    
    print(f"\n{'=' * 60}")
    print(f"STATUS: {label}")
    print(f"{'=' * 60}")
    print(f"State: {state.value}")
    print(f"Consecutive Failures: {consecutive_failures}")
    print(f"\nTimestamps:")
    print(f"  Last Check: {format_timestamp(last_check)}")
    print(f"  Last Healthy: {format_timestamp(last_healthy)}")
    print(f"  First Failure: {format_timestamp(first_failure)}")
    print(f"\nDurations:")
    print(f"  Downtime: {format_duration(downtime)}")
    print(f"  Since Last Check: {format_duration(time_since_check)}")
    print(f"  Since Last Healthy: {format_duration(time_since_healthy)}")
    print(f"{'=' * 60}")


async def demo_scenario_1():
    """
    Scenario 1: Database goes down and we track when it happened
    
    This demonstrates the solution to Issue #3.1:
    - We can determine when the database went down
    - We can calculate how long it's been down
    - We can track time since last successful connection
    """
    print("\n\n" + "=" * 60)
    print("SCENARIO 1: Database Goes Down")
    print("=" * 60)
    print("\nThis scenario demonstrates:")
    print("✓ Tracking when the database went down")
    print("✓ Calculating downtime duration")
    print("✓ Monitoring time since last healthy state")
    
    monitor = ConnectionHealthMonitor()
    
    # Initial healthy state (database is up)
    print("\n[Step 1] Database is initially healthy...")
    await monitor.mark_healthy()
    await print_status(monitor, "Database Running Normally")
    
    # Wait a bit
    await asyncio.sleep(2)
    
    # Database goes down at this point (simulated at 10:00 AM for the issue example)
    print("\n[Step 2] Database goes down...")
    await monitor.mark_unhealthy()
    await print_status(monitor, "Database Down - First Failure Detected")
    
    # Wait some time (database still down)
    await asyncio.sleep(1)
    
    # Additional health check failures
    print("\n[Step 3] Subsequent health check failures...")
    await monitor.mark_unhealthy()
    await monitor.mark_unhealthy()
    await monitor.mark_unhealthy()
    await print_status(monitor, "Database Still Down - Multiple Failures")
    
    # Show the key insight: We can now answer the questions from Issue #3.1
    print("\n\n" + "=" * 60)
    print("ANSWERING ISSUE #3.1 QUESTIONS:")
    print("=" * 60)
    
    first_failure = await monitor.get_first_failure_time()
    downtime = await monitor.get_downtime_duration()
    last_healthy = await monitor.get_last_healthy_time()
    
    print(f"\nQuestion: When did the database go down?")
    print(f"Answer: At {format_timestamp(first_failure)}")
    
    print(f"\nQuestion: How long has it been down?")
    print(f"Answer: {format_duration(downtime)}")
    
    print(f"\nQuestion: When was the last successful connection?")
    print(f"Answer: At {format_timestamp(last_healthy)}")
    
    # Recovery
    print("\n\n[Step 4] Database recovers...")
    await monitor.mark_healthy()
    await print_status(monitor, "Database Recovered")
    
    print("\nNote: After recovery, first_failure_time is cleared (None)")


async def demo_scenario_2():
    """
    Scenario 2: Health check timing
    
    Demonstrates tracking when health checks are performed.
    """
    print("\n\n" + "=" * 60)
    print("SCENARIO 2: Health Check Timing")
    print("=" * 60)
    print("\nThis scenario demonstrates:")
    print("✓ Tracking when health checks are performed")
    print("✓ Calculating time since last check")
    
    monitor = ConnectionHealthMonitor()
    
    print("\n[Step 1] Perform first health check (simulated)...")
    await monitor.mark_healthy()
    await print_status(monitor, "After First Check")
    
    # Wait
    await asyncio.sleep(1.5)
    
    print("\n[Step 2] Perform second health check...")
    await monitor.mark_healthy()
    await print_status(monitor, "After Second Check")
    
    # Calculate time between checks
    last_check = await monitor.get_last_check_time()
    time_since = await monitor.get_time_since_last_check()
    
    print(f"\nTime since last check: {format_duration(time_since)}")
    print("This allows monitoring systems to determine health check frequency")


async def demo_scenario_3():
    """
    Scenario 3: Intermittent failures
    
    Demonstrates tracking multiple failure cycles.
    """
    print("\n\n" + "=" * 60)
    print("SCENARIO 3: Intermittent Connection Issues")
    print("=" * 60)
    print("\nThis scenario demonstrates:")
    print("✓ Tracking separate failure cycles")
    print("✓ Distinguishing between different downtime periods")
    
    monitor = ConnectionHealthMonitor()
    
    # First failure cycle
    print("\n[Cycle 1] First failure...")
    await monitor.mark_unhealthy()
    first_cycle_failure = await monitor.get_first_failure_time()
    await print_status(monitor, "First Failure Cycle")
    
    await asyncio.sleep(0.5)
    
    # Recovery
    print("\n[Cycle 1] Recovery...")
    await monitor.mark_healthy()
    await print_status(monitor, "Recovered from First Failure")
    
    await asyncio.sleep(0.5)
    
    # Second failure cycle
    print("\n[Cycle 2] Second failure...")
    await monitor.mark_unhealthy()
    second_cycle_failure = await monitor.get_first_failure_time()
    await print_status(monitor, "Second Failure Cycle")
    
    print(f"\nFirst cycle started at: {format_timestamp(first_cycle_failure)}")
    print(f"Second cycle started at: {format_timestamp(second_cycle_failure)}")
    print("Each failure cycle is tracked independently")


async def main():
    """Run all demonstration scenarios."""
    print("\n" + "=" * 60)
    print("TIMESTAMP TRACKING DEMONSTRATION")
    print("Issue #3.1: No Timestamp Tracking - SOLVED")
    print("=" * 60)
    
    await demo_scenario_1()
    await demo_scenario_2()
    await demo_scenario_3()
    
    print("\n\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print("\nThe ConnectionHealthMonitor now provides:")
    print("✓ get_last_check_time() - When was the last health check?")
    print("✓ get_last_healthy_time() - When was the connection last healthy?")
    print("✓ get_first_failure_time() - When did the failure start?")
    print("✓ get_downtime_duration() - How long has it been down?")
    print("✓ get_time_since_last_check() - Time since last check")
    print("✓ get_time_since_last_healthy() - Time since last healthy")
    print("\nAll timestamps are Unix timestamps (seconds since epoch)")
    print("All durations are in seconds")
    print("All methods are async-safe and thread-safe")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
