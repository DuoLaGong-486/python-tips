#!/usr/bin/env python3
"""Async HTTP load testing for python-tips service."""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import math
import time
from dataclasses import dataclass
from typing import Any, Iterable, Optional

import httpx


@dataclass
class ScenarioResult:
    name: str
    total_requests: int
    duration_s: float
    qps: float
    p95_ms: float
    p99_ms: float
    error_rate: float
    rate_limited_rate: float


def percentile_ms(values: Iterable[float], pct: float) -> float:
    sorted_values = sorted(values)
    if not sorted_values:
        return 0.0
    k = (len(sorted_values) - 1) * (pct / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_values[int(k)] * 1000.0
    d0 = sorted_values[f] * (c - k)
    d1 = sorted_values[c] * (k - f)
    return (d0 + d1) * 1000.0


async def run_scenario(
    name: str,
    client: httpx.AsyncClient,
    method: str,
    url: str,
    concurrency: int,
    duration_s: float,
    payload: Optional[dict[str, Any]] = None,
) -> ScenarioResult:
    stop_at = time.monotonic() + duration_s

    async def worker() -> tuple[list[float], int, int, int]:
        latencies: list[float] = []
        total = 0
        errors = 0
        rate_limited = 0
        while time.monotonic() < stop_at:
            start = time.monotonic()
            try:
                response = await client.request(method, url, json=payload)
                elapsed = time.monotonic() - start
                latencies.append(elapsed)
                total += 1
                if response.status_code == 429:
                    rate_limited += 1
                if response.status_code >= 400:
                    errors += 1
            except httpx.HTTPError:
                total += 1
                errors += 1
        return latencies, total, errors, rate_limited

    tasks = [asyncio.create_task(worker()) for _ in range(concurrency)]
    results = await asyncio.gather(*tasks)

    latencies: list[float] = []
    total_requests = 0
    errors = 0
    rate_limited = 0
    for worker_latencies, worker_total, worker_errors, worker_rate_limited in results:
        latencies.extend(worker_latencies)
        total_requests += worker_total
        errors += worker_errors
        rate_limited += worker_rate_limited

    p95_ms = percentile_ms(latencies, 95)
    p99_ms = percentile_ms(latencies, 99)
    qps = total_requests / duration_s if duration_s > 0 else 0.0
    error_rate = errors / total_requests if total_requests else 0.0
    rate_limited_rate = rate_limited / total_requests if total_requests else 0.0

    return ScenarioResult(
        name=name,
        total_requests=total_requests,
        duration_s=duration_s,
        qps=qps,
        p95_ms=p95_ms,
        p99_ms=p99_ms,
        error_rate=error_rate,
        rate_limited_rate=rate_limited_rate,
    )


def format_result(result: ScenarioResult) -> str:
    return (
        f"{result.name}: total={result.total_requests} "
        f"qps={result.qps:.2f} "
        f"p95={result.p95_ms:.2f}ms "
        f"p99={result.p99_ms:.2f}ms "
        f"error_rate={result.error_rate:.2%} "
        f"rate_limited_rate={result.rate_limited_rate:.2%}"
    )


def write_csv(path: str, results: list[ScenarioResult]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "scenario",
                "total_requests",
                "duration_s",
                "qps",
                "p95_ms",
                "p99_ms",
                "error_rate",
                "rate_limited_rate",
            ]
        )
        for result in results:
            writer.writerow(
                [
                    result.name,
                    result.total_requests,
                    f"{result.duration_s:.2f}",
                    f"{result.qps:.2f}",
                    f"{result.p95_ms:.2f}",
                    f"{result.p99_ms:.2f}",
                    f"{result.error_rate:.4f}",
                    f"{result.rate_limited_rate:.4f}",
                ]
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="HTTPX load testing script")
    parser.add_argument("--host", required=True, help="Base URL, e.g. http://127.0.0.1:8000")
    parser.add_argument("--concurrency", type=int, default=50, help="Concurrent workers")
    parser.add_argument("--duration", type=float, default=10.0, help="Duration per scenario (seconds)")
    parser.add_argument("--payload-size", type=int, default=1024, help="Payload size in bytes for /echo")
    parser.add_argument("--csv", dest="csv_path", help="Optional CSV output path")
    parser.add_argument("--timeout", type=float, default=5.0, help="Request timeout in seconds")
    return parser.parse_args()


def payload_for_size(payload_size: int) -> dict[str, Any]:
    payload = {"message": "x" * max(0, payload_size)}
    payload["size"] = len(json.dumps(payload).encode("utf-8"))
    return payload


async def main() -> None:
    args = parse_args()
    base_url = args.host.rstrip("/")

    limits = httpx.Limits(max_keepalive_connections=args.concurrency, max_connections=args.concurrency)
    timeout = httpx.Timeout(args.timeout)

    payload = payload_for_size(args.payload_size)

    async with httpx.AsyncClient(limits=limits, timeout=timeout) as client:
        results = []
        results.append(
            await run_scenario(
                name="GET /healthz",
                client=client,
                method="GET",
                url=f"{base_url}/healthz",
                concurrency=args.concurrency,
                duration_s=args.duration,
            )
        )
        results.append(
            await run_scenario(
                name="POST /echo",
                client=client,
                method="POST",
                url=f"{base_url}/echo",
                concurrency=args.concurrency,
                duration_s=args.duration,
                payload=payload,
            )
        )
        results.append(
            await run_scenario(
                name="GET /rate-limited",
                client=client,
                method="GET",
                url=f"{base_url}/rate-limited",
                concurrency=args.concurrency,
                duration_s=args.duration,
            )
        )

    for result in results:
        print(format_result(result))

    if args.csv_path:
        write_csv(args.csv_path, results)
        print(f"CSV written to {args.csv_path}")


if __name__ == "__main__":
    asyncio.run(main())
