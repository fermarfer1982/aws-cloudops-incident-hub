#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import boto3


@dataclass(frozen=True)
class MetricSpec:
    metric_id: str
    namespace: str
    metric_name: str
    dimensions: tuple[tuple[str, str], ...]
    stat: str
    unit: str | None = None


def parse_utc(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def metric_query(spec: MetricSpec, period: int) -> dict[str, Any]:
    metric: dict[str, Any] = {
        "Namespace": spec.namespace,
        "MetricName": spec.metric_name,
        "Dimensions": [
            {"Name": name, "Value": value} for name, value in spec.dimensions
        ],
    }
    if spec.unit:
        metric["Unit"] = spec.unit
    return {
        "Id": spec.metric_id,
        "MetricStat": {
            "Metric": metric,
            "Period": period,
            "Stat": spec.stat,
        },
        "ReturnData": True,
    }


def build_specs(args: argparse.Namespace) -> list[MetricSpec]:
    api_dimensions = (("ApiId", args.api_id), ("Stage", "$default"))
    api_lambda = (("FunctionName", args.api_function_name),)
    processor_lambda = (("FunctionName", args.processor_function_name),)
    queue = (("QueueName", args.processing_queue_name),)
    dlq = (("QueueName", args.processing_dlq_name),)
    incidents = (("TableName", args.table_name),)
    metrics = (("TableName", args.metrics_table_name),)

    return [
        MetricSpec("api_count", "AWS/ApiGateway", "Count", api_dimensions, "Sum"),
        MetricSpec("api_4xx", "AWS/ApiGateway", "4xx", api_dimensions, "Sum"),
        MetricSpec("api_5xx", "AWS/ApiGateway", "5xx", api_dimensions, "Sum"),
        MetricSpec("api_latency_p95", "AWS/ApiGateway", "Latency", api_dimensions, "p95"),
        MetricSpec(
            "api_integration_latency_p95",
            "AWS/ApiGateway",
            "IntegrationLatency",
            api_dimensions,
            "p95",
        ),
        MetricSpec("lambda_api_invocations", "AWS/Lambda", "Invocations", api_lambda, "Sum"),
        MetricSpec("lambda_api_errors", "AWS/Lambda", "Errors", api_lambda, "Sum"),
        MetricSpec("lambda_api_throttles", "AWS/Lambda", "Throttles", api_lambda, "Sum"),
        MetricSpec("lambda_api_duration_p95", "AWS/Lambda", "Duration", api_lambda, "p95"),
        MetricSpec(
            "lambda_api_concurrent_max",
            "AWS/Lambda",
            "ConcurrentExecutions",
            api_lambda,
            "Maximum",
        ),
        MetricSpec(
            "lambda_processor_invocations",
            "AWS/Lambda",
            "Invocations",
            processor_lambda,
            "Sum",
        ),
        MetricSpec("lambda_processor_errors", "AWS/Lambda", "Errors", processor_lambda, "Sum"),
        MetricSpec(
            "lambda_processor_throttles",
            "AWS/Lambda",
            "Throttles",
            processor_lambda,
            "Sum",
        ),
        MetricSpec(
            "lambda_processor_duration_p95",
            "AWS/Lambda",
            "Duration",
            processor_lambda,
            "p95",
        ),
        MetricSpec(
            "lambda_processor_concurrent_max",
            "AWS/Lambda",
            "ConcurrentExecutions",
            processor_lambda,
            "Maximum",
        ),
        MetricSpec("sqs_sent", "AWS/SQS", "NumberOfMessagesSent", queue, "Sum"),
        MetricSpec("sqs_received", "AWS/SQS", "NumberOfMessagesReceived", queue, "Sum"),
        MetricSpec("sqs_deleted", "AWS/SQS", "NumberOfMessagesDeleted", queue, "Sum"),
        MetricSpec(
            "sqs_visible_max",
            "AWS/SQS",
            "ApproximateNumberOfMessagesVisible",
            queue,
            "Maximum",
        ),
        MetricSpec(
            "sqs_oldest_age_max",
            "AWS/SQS",
            "ApproximateAgeOfOldestMessage",
            queue,
            "Maximum",
        ),
        MetricSpec(
            "dlq_visible_max",
            "AWS/SQS",
            "ApproximateNumberOfMessagesVisible",
            dlq,
            "Maximum",
        ),
        MetricSpec(
            "ddb_incidents_read_units",
            "AWS/DynamoDB",
            "ConsumedReadCapacityUnits",
            incidents,
            "Sum",
        ),
        MetricSpec(
            "ddb_incidents_write_units",
            "AWS/DynamoDB",
            "ConsumedWriteCapacityUnits",
            incidents,
            "Sum",
        ),
        MetricSpec(
            "ddb_incidents_read_throttles",
            "AWS/DynamoDB",
            "ReadThrottleEvents",
            incidents,
            "Sum",
        ),
        MetricSpec(
            "ddb_incidents_write_throttles",
            "AWS/DynamoDB",
            "WriteThrottleEvents",
            incidents,
            "Sum",
        ),
        MetricSpec(
            "ddb_metrics_read_units",
            "AWS/DynamoDB",
            "ConsumedReadCapacityUnits",
            metrics,
            "Sum",
        ),
        MetricSpec(
            "ddb_metrics_write_units",
            "AWS/DynamoDB",
            "ConsumedWriteCapacityUnits",
            metrics,
            "Sum",
        ),
        MetricSpec(
            "ddb_metrics_read_throttles",
            "AWS/DynamoDB",
            "ReadThrottleEvents",
            metrics,
            "Sum",
        ),
        MetricSpec(
            "ddb_metrics_write_throttles",
            "AWS/DynamoDB",
            "WriteThrottleEvents",
            metrics,
            "Sum",
        ),
    ]


def aggregate(values: list[float], stat: str) -> float | None:
    if not values:
        return None
    if stat == "Sum":
        return round(sum(values), 4)
    return round(max(values), 4)


def collect(args: argparse.Namespace) -> dict[str, Any]:
    start = parse_utc(args.start_time) - timedelta(minutes=args.padding_minutes)
    end = parse_utc(args.end_time) + timedelta(minutes=args.padding_minutes)
    specs = build_specs(args)
    by_id = {spec.metric_id: spec for spec in specs}

    client = boto3.client("cloudwatch", region_name=args.region)
    response = client.get_metric_data(
        MetricDataQueries=[metric_query(spec, args.period) for spec in specs],
        StartTime=start,
        EndTime=end,
        ScanBy="TimestampAscending",
    )

    results: dict[str, Any] = {}
    for result in response.get("MetricDataResults", []):
        metric_id = result["Id"]
        spec = by_id[metric_id]
        timestamps = result.get("Timestamps", [])
        values = [float(value) for value in result.get("Values", [])]
        points = [
            {"timestamp": timestamp.astimezone(timezone.utc).isoformat(), "value": value}
            for timestamp, value in zip(timestamps, values, strict=True)
        ]
        results[metric_id] = {
            "namespace": spec.namespace,
            "metric_name": spec.metric_name,
            "dimensions": dict(spec.dimensions),
            "stat": spec.stat,
            "status_code": result.get("StatusCode"),
            "messages": result.get("Messages", []),
            "aggregate": aggregate(values, spec.stat),
            "points": points,
        }

    missing = sorted(spec.metric_id for spec in specs if not results.get(spec.metric_id, {}).get("points"))
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "region": args.region,
        "requested_window": {
            "test_start": parse_utc(args.start_time).isoformat(),
            "test_end": parse_utc(args.end_time).isoformat(),
            "query_start": start.isoformat(),
            "query_end": end.isoformat(),
            "period_seconds": args.period,
        },
        "resources": {
            "api_id": args.api_id,
            "api_function_name": args.api_function_name,
            "processor_function_name": args.processor_function_name,
            "processing_queue_name": args.processing_queue_name,
            "processing_dlq_name": args.processing_dlq_name,
            "table_name": args.table_name,
            "metrics_table_name": args.metrics_table_name,
        },
        "metrics": results,
        "metrics_without_datapoints": missing,
        "limitations": [
            "CloudWatch service metrics can arrive after the workflow collection window.",
            "This evidence does not include final billing data or Cost Explorer allocation.",
            "An ephemeral run is not proof of sustained production capacity.",
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect AWS service metrics for one load-test window.")
    parser.add_argument("--region", required=True)
    parser.add_argument("--start-time", required=True)
    parser.add_argument("--end-time", required=True)
    parser.add_argument("--api-id", required=True)
    parser.add_argument("--api-function-name", required=True)
    parser.add_argument("--processor-function-name", required=True)
    parser.add_argument("--processing-queue-name", required=True)
    parser.add_argument("--processing-dlq-name", required=True)
    parser.add_argument("--table-name", required=True)
    parser.add_argument("--metrics-table-name", required=True)
    parser.add_argument("--period", type=int, default=60)
    parser.add_argument("--padding-minutes", type=int, default=5)
    parser.add_argument("--output", default="evidence/aws-service-metrics.json")
    args = parser.parse_args()
    if args.period < 1:
        parser.error("--period must be positive")
    if args.padding_minutes < 0 or args.padding_minutes > 30:
        parser.error("--padding-minutes must be between 0 and 30")
    if parse_utc(args.end_time) <= parse_utc(args.start_time):
        parser.error("--end-time must be after --start-time")
    return args


def main() -> int:
    args = parse_args()
    report = collect(args)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Collected {len(report['metrics'])} metric series")
    print(f"Metrics without datapoints: {len(report['metrics_without_datapoints'])}")
    print(f"Report: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
