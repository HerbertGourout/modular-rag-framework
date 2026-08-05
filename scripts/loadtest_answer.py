"""Overload/soak smoke test for `POST /answer` (Lot 16c, docs/refactoring-plan.md
— "overload/backpressure semantics (need live load-testing infra)", deferred
from Lot 14). Needs a running deployment to point at (the container built in
Lot 16b, or `uvicorn server:app` directly) — this script was never executed
in the sandboxed environment it was written in (no reachable deployment
target there); run it for real and record the results as this lot's
overload evidence. See docs/guides/backup-restore.md's "Overload / soak
evidence" section for how to read the output.

Usage:
    python scripts/loadtest_answer.py --url http://localhost:8000 --concurrency 20 --requests 200
"""
from __future__ import annotations

import argparse
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx


def _one_request(url: str) -> tuple[int, float]:
    t0 = time.perf_counter()
    try:
        resp = httpx.post(f"{url}/answer", json={"question": "What is RAG?"}, timeout=30.0)
        return resp.status_code, time.perf_counter() - t0
    except httpx.HTTPError:
        return 0, time.perf_counter() - t0


def main() -> None:
    parser = argparse.ArgumentParser(description="Overload/soak smoke test for POST /answer.")
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--concurrency", type=int, default=20)
    parser.add_argument("--requests", type=int, default=200)
    args = parser.parse_args()

    latencies: list[float] = []
    statuses: dict[int, int] = {}
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = [pool.submit(_one_request, args.url) for _ in range(args.requests)]
        for future in as_completed(futures):
            status, latency = future.result()
            statuses[status] = statuses.get(status, 0) + 1
            latencies.append(latency)

    latencies.sort()
    p95 = latencies[int(0.95 * len(latencies))] if latencies else 0.0
    print(f"Status code counts: {statuses}")
    print(f"p50={statistics.median(latencies):.3f}s  p95={p95:.3f}s  max={max(latencies):.3f}s")
    print(
        f"429 (rate-limited) count: {statuses.get(429, 0)} -- expected under load if "
        "rate_limit_per_minute is below (concurrency * requests / duration)"
    )


if __name__ == "__main__":
    main()
