#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import statistics
import time
import uuid
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


@dataclass(frozen=True)
class Sample:
    operation: str
    status_code: int
    latency_ms: float
    success: bool
    error: str | None = None


def percentile(values: list[float], percentile_value: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percentile_value
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def latency_summary(samples: list[Sample]) -> dict[str, float]:
    values = [sample.latency_ms for sample in samples]
    if not values:
        return {
            "min": 0.0,
            "mean": 0.0,
            "p50": 0.0,
            "p95": 0.0,
            "p99": 0.0,
            "max": 0.0,
        }
    return {
        "min": round(min(values), 2),
        "mean": round(statistics.fmean(values), 2),
        "p50": round(percentile(values, 0.50), 2),
        "p95": round(percentile(values, 0.95), 2),
        "p99": round(percentile(values, 0.99), 2),
        "max": round(max(values), 2),
    }


def summarize(samples: list[Sample], elapsed_seconds: float) -> dict[str, Any]:
    total = len(samples)
    successful = sum(sample.success for sample in samples)
    failed = total - successful
    by_operation: dict[str, list[Sample]] = defaultdict(list)
    for sample in samples:
        by_operation[sample.operation].append(sample)

    operations = {}
    for operation, operation_samples in sorted(by_operation.items()):
        operation_successful = sum(sample.success for sample in operation_samples)
        operation_total = len(operation_samples)
        operations[operation] = {
            "requests": operation_total,
            "successful": operation_successful,
            "failed": operation_total - operation_successful,
            "latency_ms": latency_summary(operation_samples),
        }

    return {
        "requests": total,
        "successful": successful,
        "failed": failed,
        "error_rate_percent": round((failed / total * 100) if total else 100.0, 4),
        "requests_per_second": round(total / elapsed_seconds if elapsed_seconds else 0.0, 2),
        "latency_ms": latency_summary(samples),
        "status_codes": dict(sorted(Counter(sample.status_code for sample in samples).items())),
        "operations": operations,
    }


async def measured_request(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    *,
    operation: str,
    expected_statuses: set[int],
    **kwargs: Any,
) -> tuple[Sample, httpx.Response | None]:
    started = time.perf_counter()
    try:
        response = await client.request(method, path, **kwargs)
        elapsed_ms = (time.perf_counter() - started) * 1000
        success = response.status_code in expected_statuses
        error = None if success else response.text[:300]
        return (
            Sample(
                operation=operation,
                status_code=response.status_code,
                latency_ms=elapsed_ms,
                success=success,
                error=error,
            ),
            response,
        )
    except httpx.HTTPError as exc:
        elapsed_ms = (time.perf_counter() - started) * 1000
        return (
            Sample(
                operation=operation,
                status_code=0,
                latency_ms=elapsed_ms,
                success=False,
                error=str(exc),
            ),
            None,
        )


async def worker(
    worker_id: int,
    client: httpx.AsyncClient,
    *,
    deadline: float,
    write_percent: float,
    samples: list[Sample],
) -> None:
    sequence = 0
    while time.monotonic() < deadline:
        sequence += 1
        choice = random.random() * 100

        if choice < write_percent:
            payload = {
                "source": f"load-worker-{worker_id:03d}",
                "site": "LoadTest",
                "type": "LOAD_TEST_EVENT",
                "message": f"Synthetic load event {worker_id}-{sequence}-{uuid.uuid4().hex[:8]}",
                "metadata": {"synthetic": True, "worker": worker_id},
            }
            sample, _ = await measured_request(
                client,
                "POST",
                "/events",
                operation="POST /events",
                expected_statuses={201, 202},
                json=payload,
            )
            samples.append(sample)
        elif choice < write_percent + 20:
            sample, _ = await measured_request(
                client,
                "GET",
                "/metrics",
                operation="GET /metrics",
                expected_statuses={200},
            )
            samples.append(sample)
        else:
            sample, response = await measured_request(
                client,
                "GET",
                "/events",
                operation="GET /events page 1",
                expected_statuses={200},
                params={"limit": 25},
            )
            samples.append(sample)
            if response is not None and sample.success:
                next_token = response.headers.get("x-next-token")
                if next_token and random.random() < 0.5:
                    next_sample, _ = await measured_request(
                        client,
                        "GET",
                        "/events",
                        operation="GET /events page 2",
                        expected_statuses={200},
                        params={"limit": 25, "next_token": next_token},
                    )
                    samples.append(next_sample)

        await asyncio.sleep(random.uniform(0.01, 0.08))


async def run(args: argparse.Namespace) -> tuple[dict[str, Any], bool]:
    headers = {"Accept": "application/json"}
    if args.bearer_token:
        headers["Authorization"] = f"Bearer {args.bearer_token}"

    limits = httpx.Limits(
        max_connections=max(args.concurrency * 2, 20),
        max_keepalive_connections=max(args.concurrency, 10),
    )
    timeout = httpx.Timeout(args.request_timeout)

    async with httpx.AsyncClient(
        base_url=args.base_url.rstrip("/"),
        headers=headers,
        timeout=timeout,
        limits=limits,
    ) as client:
        health = await client.get("/health")
        health.raise_for_status()

        samples: list[Sample] = []
        started_at = datetime.now(timezone.utc)
        started = time.monotonic()
        deadline = started + args.duration
        await asyncio.gather(
            *(
                worker(
                    worker_id,
                    client,
                    deadline=deadline,
                    write_percent=args.write_percent,
                    samples=samples,
                )
                for worker_id in range(args.concurrency)
            )
        )
        elapsed = time.monotonic() - started

    summary = summarize(samples, elapsed)
    threshold_failures = []
    if summary["error_rate_percent"] > args.max_error_rate:
        threshold_failures.append(
            f"error rate {summary['error_rate_percent']}% exceeds {args.max_error_rate}%"
        )
    if summary["latency_ms"]["p95"] > args.max_p95_ms:
        threshold_failures.append(
            f"p95 {summary['latency_ms']['p95']}ms exceeds {args.max_p95_ms}ms"
        )

    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "started_at": started_at.isoformat(),
        "target": args.base_url.rstrip("/"),
        "configuration": {
            "duration_seconds": args.duration,
            "actual_elapsed_seconds": round(elapsed, 3),
            "concurrency": args.concurrency,
            "write_percent": args.write_percent,
            "request_timeout_seconds": args.request_timeout,
            "thresholds": {
                "max_error_rate_percent": args.max_error_rate,
                "max_p95_ms": args.max_p95_ms,
            },
        },
        "summary": summary,
        "thresholds_passed": not threshold_failures,
        "threshold_failures": threshold_failures,
        "failed_samples": [
            asdict(sample) for sample in samples if not sample.success
        ][:50],
    }
    return report, not threshold_failures


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a bounded asynchronous load test against CloudOps Incident Hub.",
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("LOAD_TEST_BASE_URL", "http://localhost:8080"),
    )
    parser.add_argument("--duration", type=int, default=30)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--write-percent", type=float, default=0.0)
    parser.add_argument("--request-timeout", type=float, default=10.0)
    parser.add_argument("--max-error-rate", type=float, default=1.0)
    parser.add_argument("--max-p95-ms", type=float, default=2000.0)
    parser.add_argument(
        "--bearer-token",
        default=os.getenv("LOAD_TEST_BEARER_TOKEN"),
        help="Cognito access token for protected AWS endpoints.",
    )
    parser.add_argument(
        "--output",
        default="artifacts/load-test-report.json",
    )
    args = parser.parse_args()

    if args.duration < 1:
        parser.error("--duration must be at least 1 second")
    if args.concurrency < 1 or args.concurrency > 500:
        parser.error("--concurrency must be between 1 and 500")
    if args.write_percent < 0 or args.write_percent > 50:
        parser.error("--write-percent must be between 0 and 50")
    if args.request_timeout <= 0:
        parser.error("--request-timeout must be greater than zero")
    if args.max_error_rate < 0 or args.max_error_rate > 100:
        parser.error("--max-error-rate must be between 0 and 100")
    if args.max_p95_ms <= 0:
        parser.error("--max-p95-ms must be greater than zero")
    return args


def main() -> int:
    args = parse_args()
    try:
        report, passed = asyncio.run(run(args))
    except (httpx.HTTPError, OSError) as exc:
        print(f"Load test could not start: {exc}")
        return 2

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    summary = report["summary"]
    print(f"Requests: {summary['requests']}")
    print(f"Throughput: {summary['requests_per_second']} req/s")
    print(f"Errors: {summary['error_rate_percent']}%")
    print(f"Latency p50/p95/p99: {summary['latency_ms']['p50']}/"
          f"{summary['latency_ms']['p95']}/{summary['latency_ms']['p99']} ms")
    print(f"Report: {output}")
    if not passed:
        for failure in report["threshold_failures"]:
            print(f"Threshold failed: {failure}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
