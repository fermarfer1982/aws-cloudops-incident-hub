# AWS cost-governance evidence — 2026-07-12

## Status

**Validated for the AWS laboratory account.**

This document records sanitized, read-only evidence of AWS Budgets and Cost
Anomaly Detection controls configured at account level.

The evidence does not contain the AWS account identifier, email addresses,
credentials or subscriber destinations.

No application stack was deployed and no AWS resource was created, modified or
deleted during collection.

## Collection

| Field | Value |
|---|---|
| Date | 2026-07-12 |
| Method | AWS CLI read-only queries from AWS CloudShell |
| Identity validation | Expected laboratory account confirmed |
| Account identifier committed | No |
| Email addresses committed | No |
| Application stack deployed | No |
| AWS resources modified | No |

Machine-readable evidence:

```text
docs/evidence/aws-cost-governance-2026-07-12.json
```

## AWS Budgets

| Budget | Period | Limit | Spend at collection |
|---|---|---:|---:|
| `cloudops-lab-monthly` | Monthly | 5.00 USD | 0.001 USD |
| `cloudops-zero-spend` | Monthly | 1.00 USD | 0.001 USD |

No forecasted-spend value was returned at collection time.

## Budget notifications

| Budget | Signal | Threshold | State | Subscriber |
|---|---|---:|---|---|
| `cloudops-lab-monthly` | Actual | 85 | OK | 1 EMAIL |
| `cloudops-lab-monthly` | Actual | 100 | OK | 1 EMAIL |
| `cloudops-lab-monthly` | Forecasted | 100 | OK | 1 EMAIL |
| `cloudops-zero-spend` | Actual | 0.01 USD absolute | OK | 1 EMAIL |
| `cloudops-zero-spend` | Actual | 100 | OK | 1 EMAIL |
| `cloudops-zero-spend` | Forecasted | 100 | OK | 1 EMAIL |

Where AWS did not return `ThresholdType`, the machine-readable evidence retains
the value as `null` instead of inferring it.

The name `cloudops-zero-spend` represents an early-warning objective. It is not a
hard zero-cost control: its budget limit is 1 USD and its earliest actual-spend
notification is triggered above 0.01 USD.

## Cost Anomaly Detection

The account contains the service-dimensional monitor:

```text
Default-Services-Monitor
```

AWS returned no `LastEvaluatedDate` at collection time. This proves that the
monitor is configured, but it does not prove that an anomaly has already been
evaluated or delivered.

Two daily subscriptions were observed:

| Subscription | Condition | Subscriber |
|---|---|---|
| `Default-Services-Subscription` | Absolute impact at least 100 USD and percentage impact at least 40% | Confirmed EMAIL |
| `cloudops-daily-anomalies` | Absolute impact at least 1 USD | Confirmed EMAIL |

## Assessment

The AWS laboratory account has:

- Two monthly cost budgets.
- Actual and forecasted budget notifications.
- A confirmed subscriber for each budget notification.
- A service-dimensional Cost Anomaly Detection monitor.
- Two daily anomaly subscriptions.
- Confirmed subscriber status for both anomaly subscriptions.
- An acting laboratory cost owner defined in `docs/workload-ownership.md`.

## Differences from the production target

The suggested production pattern in `docs/cost-controls.md` proposes actual-spend
notifications at 50%, 80% and 100%, plus forecasted spend at 80%.

The observed laboratory configuration uses:

- Actual 85% and 100%, plus forecasted 100%, for
  `cloudops-lab-monthly`.
- Actual 0.01 USD absolute, actual 100% and forecasted 100% for
  `cloudops-zero-spend`.

The evidence records the real configuration and does not claim that it matches the
suggested production pattern.

## Remaining production gaps

The following remain open:

- Evidence that cost-allocation tags are activated.
- A production-specific budget and approved monthly amount.
- Post-billing review after charges have fully appeared.
- Cost per 1,000 incidents.
- Forecasting based on sustained representative traffic.
- A decision about Budget Actions or another hard-stop mechanism.
- Organizational cost ownership and separation of duties.

AWS Budgets and anomaly notifications provide alerts. They are not guaranteed hard
spending caps.

## Well-Architected outcome

- **WA-011:** completed for the AWS laboratory account.
- **COST-01:** closed for laboratory budgets and anomaly-monitor configuration.
- Production financial governance remains incomplete.
- The workload remains not production-ready.
