from __future__ import annotations

import argparse
import asyncio
import json
from math import ceil
from time import perf_counter

import httpx


QUERIES = [
    "象鼻山在哪里？",
    "两江四湖包括哪些地方？",
    "桂林两天怎么玩？",
    "明天桂林天气怎么样？",
]


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, ceil(p * len(ordered)) - 1))
    return round(ordered[index], 3)


async def run_load(
    *,
    base_url: str,
    request_count: int,
    concurrency: int,
    timeout: float,
    api_key: str | None,
) -> dict:
    semaphore = asyncio.Semaphore(concurrency)
    latencies: list[float] = []
    errors: list[str] = []
    headers = {"X-API-Key": api_key} if api_key else {}

    async with httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=timeout, headers=headers) as client:
        async def one(index: int) -> None:
            async with semaphore:
                started = perf_counter()
                try:
                    response = await client.post(
                        "/api/v1/chat",
                        json={"message": QUERIES[index % len(QUERIES)]},
                    )
                    if response.status_code != 200:
                        errors.append(f"{response.status_code}:{response.text[:120]}")
                except Exception as exc:
                    errors.append(type(exc).__name__)
                finally:
                    latencies.append((perf_counter() - started) * 1000)

        started = perf_counter()
        await asyncio.gather(*(one(index) for index in range(request_count)))
        duration = perf_counter() - started

    success = request_count - len(errors)
    return {
        "requests": request_count,
        "success": success,
        "errors": len(errors),
        "error_rate": round(len(errors) / request_count, 4) if request_count else 0.0,
        "duration_seconds": round(duration, 3),
        "throughput_rps": round(request_count / duration, 3) if duration else 0.0,
        "latency_ms": {
            "p50": percentile(latencies, 0.50),
            "p95": percentile(latencies, 0.95),
            "max": round(max(latencies), 3) if latencies else 0.0,
        },
        "sample_errors": errors[:5],
    }


async def _main() -> int:
    parser = argparse.ArgumentParser(description="Small concurrent load smoke for the chat API.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--api-key", default="")
    parser.add_argument("--max-p95-ms", type=float, default=2000.0)
    parser.add_argument("--max-error-rate", type=float, default=0.01)
    args = parser.parse_args()

    result = await run_load(
        base_url=args.base_url,
        request_count=args.requests,
        concurrency=args.concurrency,
        timeout=args.timeout,
        api_key=args.api_key or None,
    )
    result["thresholds"] = {
        "max_p95_ms": args.max_p95_ms,
        "max_error_rate": args.max_error_rate,
    }
    result["passed"] = (
        result["latency_ms"]["p95"] <= args.max_p95_ms
        and result["error_rate"] <= args.max_error_rate
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
