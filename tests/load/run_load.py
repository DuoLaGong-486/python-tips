import asyncio
import os
import time
import urllib.request

from .config import (
    DEFAULT_CONCURRENCY,
    DEFAULT_DURATION_SECONDS,
    DEFAULT_PAYLOAD_SIZE_BYTES,
    DEFAULT_TARGET_URL,
)


def _get_env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    return int(value)


def _get_env_str(name: str, default: str) -> str:
    value = os.getenv(name)
    if value is None:
        return default
    return value


def _make_payload(size_bytes: int) -> bytes:
    return b"x" * size_bytes


def _send_request(url: str, payload: bytes) -> int:
    request = urllib.request.Request(url, data=payload, method="POST")
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.status


async def _worker(url: str, payload: bytes, end_time: float, latencies: list[float]) -> int:
    errors = 0
    while time.time() < end_time:
        start = time.perf_counter()
        try:
            status = await asyncio.to_thread(_send_request, url, payload)
            if status >= 400:
                errors += 1
        except Exception:
            errors += 1
        else:
            latencies.append(time.perf_counter() - start)
    return errors


async def run_load_test() -> None:
    concurrency = _get_env_int("LOAD_USERS", DEFAULT_CONCURRENCY)
    duration = _get_env_int("LOAD_DURATION", DEFAULT_DURATION_SECONDS)
    payload_size = _get_env_int("LOAD_PAYLOAD_SIZE", DEFAULT_PAYLOAD_SIZE_BYTES)
    target_url = _get_env_str("LOAD_URL", DEFAULT_TARGET_URL)

    payload = _make_payload(payload_size)
    end_time = time.time() + duration
    latencies: list[float] = []

    tasks = [
        asyncio.create_task(_worker(target_url, payload, end_time, latencies))
        for _ in range(concurrency)
    ]
    error_counts = await asyncio.gather(*tasks)
    errors = sum(error_counts)

    if latencies:
        sorted_latencies = sorted(latencies)
        index = max(int(len(sorted_latencies) * 0.95) - 1, 0)
        p95 = sorted_latencies[index] * 1000
        avg = sum(sorted_latencies) / len(sorted_latencies) * 1000
    else:
        p95 = 0.0
        avg = 0.0

    total_requests = len(latencies) + errors
    error_rate = (errors / total_requests) * 100 if total_requests else 0.0

    print("Load test complete")
    print(f"Target URL: {target_url}")
    print(f"Concurrency: {concurrency}")
    print(f"Duration (s): {duration}")
    print(f"Payload size (bytes): {payload_size}")
    print(f"Total requests: {total_requests}")
    print(f"Errors: {errors} ({error_rate:.2f}%)")
    print(f"Average latency (ms): {avg:.2f}")
    print(f"P95 latency (ms): {p95:.2f}")


if __name__ == "__main__":
    asyncio.run(run_load_test())
