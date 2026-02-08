import argparse
import asyncio
import json
import os
import time

import httpx


def parse_args():
    parser = argparse.ArgumentParser(description="Async load test for FastAPI.")
    parser.add_argument("--base-url", default=os.getenv("BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--concurrency", type=int, default=int(os.getenv("CONCURRENCY", "50")))
    parser.add_argument("--requests", type=int, default=int(os.getenv("REQUESTS", "500")))
    parser.add_argument("--payload-size", type=int, default=int(os.getenv("PAYLOAD_SIZE", "128")))
    return parser.parse_args()


def build_payload(size):
    return {"message": "x" * size}


async def worker(client, base_url, payload, results, index):
    start = time.perf_counter()
    response = await client.post(f"{base_url}/echo", json=payload)
    duration = time.perf_counter() - start
    results[index] = (response.status_code, duration)


async def run_load_test(base_url, concurrency, total_requests, payload_size):
    payload = build_payload(payload_size)
    results = [None] * total_requests
    limits = httpx.Limits(max_connections=concurrency, max_keepalive_connections=concurrency)
    async with httpx.AsyncClient(limits=limits, timeout=10) as client:
        for batch_start in range(0, total_requests, concurrency):
            batch_end = min(batch_start + concurrency, total_requests)
            tasks = []
            for i in range(batch_start, batch_end):
                tasks.append(worker(client, base_url, payload, results, i))
            await asyncio.gather(*tasks)
    return results


def summarize(results):
    durations = [duration for _, duration in results if duration is not None]
    status_codes = {}
    for status_code, _ in results:
        status_codes[status_code] = status_codes.get(status_code, 0) + 1
    durations.sort()
    total = len(durations)
    p95_index = int(total * 0.95) - 1 if total else 0
    p99_index = int(total * 0.99) - 1 if total else 0
    summary = {
        "total_requests": total,
        "p95_latency_ms": round(durations[p95_index] * 1000, 2) if total else 0,
        "p99_latency_ms": round(durations[p99_index] * 1000, 2) if total else 0,
        "status_codes": status_codes,
    }
    return summary


def main():
    args = parse_args()
    start = time.perf_counter()
    results = asyncio.run(
        run_load_test(
            base_url=args.base_url,
            concurrency=args.concurrency,
            total_requests=args.requests,
            payload_size=args.payload_size,
        )
    )
    duration = time.perf_counter() - start
    summary = summarize(results)
    summary["duration_sec"] = round(duration, 2)
    summary["throughput_rps"] = round(summary["total_requests"] / duration, 2) if duration else 0
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
