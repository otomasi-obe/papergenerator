#!/usr/bin/env python3
"""
PaperFull.app — Simple Load Test
Measures: requests/sec, p95 latency, error rate
Usage: python3 loadtest.py [concurrent_users] [duration_seconds]
"""
import asyncio
import aiohttp
import time
import statistics
import sys
from collections import defaultdict

# Test endpoints
ENDPOINTS = [
    ("GET", "http://localhost:8000/", "homepage"),
    ("GET", "http://localhost:8000/api/health", "health"),
    # Add more endpoints as needed
]

async def make_request(session, method, url, label):
    """Single request with timing."""
    start = time.perf_counter()
    try:
        async with session.request(method, url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            await resp.read()
            elapsed = time.perf_counter() - start
            return {
                "label": label,
                "status": resp.status,
                "time": elapsed,
                "error": None,
            }
    except Exception as e:
        elapsed = time.perf_counter() - start
        return {
            "label": label,
            "status": 0,
            "time": elapsed,
            "error": str(e)[:50],
        }


async def run_load_test(concurrent: int, duration: int):
    """Run load test for specified duration."""
    print(f"\n{'='*60}")
    print(f" PaperFull.app Load Test")
    print(f"{'='*60}")
    print(f"Concurrent users: {concurrent}")
    print(f"Duration: {duration}s")
    print(f"Endpoints: {len(ENDPOINTS)}")
    print(f"{'='*60}\n")

    results = defaultdict(list)
    start_time = time.perf_counter()
    request_count = 0

    async with aiohttp.ClientSession() as session:
        async def worker():
            nonlocal request_count
            while time.perf_counter() - start_time < duration:
                for method, url, label in ENDPOINTS:
                    result = await make_request(session, method, url, label)
                    results[label].append(result)
                    request_count += 1
                    await asyncio.sleep(0.01)  # Small delay between requests

        # Start workers
        tasks = [asyncio.create_task(worker()) for _ in range(concurrent)]
        await asyncio.gather(*tasks)

    total_time = time.perf_counter() - start_time

    # Print results
    print(f"\n{'='*60}")
    print(f" RESULTS")
    print(f"{'='*60}")
    print(f"Total time: {total_time:.2f}s")
    print(f"Total requests: {request_count}")
    print(f"Requests/sec: {request_count / total_time:.1f}")
    print()

    for label, data in results.items():
        times = [r["time"] for r in data]
        errors = sum(1 for r in data if r["error"] or r["status"] >= 400)
        success = len(data) - errors

        if times:
            print(f"  {label}:")
            print(f"    Requests: {len(data)}")
            print(f"    Success: {success} ({100*success/len(data):.1f}%)")
            print(f"    Errors: {errors}")
            print(f"    Avg latency: {statistics.mean(times)*1000:.1f}ms")
            print(f"    P50 latency: {statistics.median(times)*1000:.1f}ms")
            if len(times) >= 2:
                print(f"    P95 latency: {sorted(times)[int(len(times)*0.95)]*1000:.1f}ms")
                print(f"    P99 latency: {sorted(times)[int(len(times)*0.99)]*1000:.1f}ms")
            print()

    print(f"{'='*60}\n")


if __name__ == "__main__":
    concurrent = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    duration = int(sys.argv[2]) if len(sys.argv) > 2 else 30

    print(f"\nStarting load test in 3 seconds...")
    print(f"Press Ctrl+C to abort")
    time.sleep(3)

    asyncio.run(run_load_test(concurrent, duration))
