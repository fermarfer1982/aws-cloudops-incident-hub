# Provisional service-level objectives

## Status

These SLOs are initial engineering objectives for a future persistent environment. They are not contractual commitments and are not considered validated until representative load and game-day evidence exists.

## User journeys

1. Submit a valid incident.
2. Read recent incidents.
3. Read aggregate operational metrics.
4. Change an incident workflow status.
5. Process an accepted incident asynchronously into DynamoDB.

## Initial objectives

| Indicator | Objective | Window | Notes |
|---|---:|---:|---|
| API availability | 99.9% successful authorized requests | Rolling 30 days | Excludes invalid credentials, malformed requests and planned maintenance. |
| API latency | 95% below 2 seconds | Rolling 30 days | Measured at API Gateway, not only Lambda duration. |
| Asynchronous processing latency | 99% persisted within 60 seconds | Rolling 30 days | Measured from EventBridge acceptance to incident availability. |
| DLQ health | Zero unacknowledged messages for more than 30 minutes | Continuous | Any DLQ message requires triage. |
| Queue age | Oldest message below 300 seconds | Continuous | Existing CloudWatch alarm evaluates two consecutive five-minute periods. |
| Data durability | Incident RPO at or below 15 minutes | Per recovery exercise | Requires PITR and measured restore evidence. |

## Error budget

For a 99.9% monthly availability objective, the nominal error budget is approximately 43 minutes in a 30-day month. This figure is only meaningful after the workload has:

- a stable traffic definition,
- end-to-end API Gateway metrics,
- agreed exclusions,
- an approved maintenance policy,
- and an accountable service owner.

## Alert mapping

| Signal | Current alarm | Operator response |
|---|---|---|
| API Lambda errors | `cloudops-api-function-errors` | Check logs, recent deployment and EventBridge publishing. |
| Processor errors | `cloudops-processor-function-errors` | Inspect failed SQS batch records and application logs. |
| Queue age | `cloudops-processing-queue-age` | Check throttling, concurrency, poison messages and downstream DynamoDB errors. |
| DLQ messages | `cloudops-processing-dlq-messages` | Follow the DLQ investigation and redrive runbook. |

The existing alarms are operational symptoms, not a complete SLO measurement system. Production readiness still requires API Gateway availability and latency dashboards, burn-rate alerting and ownership.

## Review cadence

Review these objectives after:

- the first persistent deployment,
- every material traffic change,
- a severity-one incident,
- a recovery exercise,
- or at least every six months.
