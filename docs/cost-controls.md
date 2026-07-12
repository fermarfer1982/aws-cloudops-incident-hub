# Cost controls for persistent environments

The workload stack deliberately does not create AWS Budgets or Cost Anomaly Detection resources. Those controls belong at the account or organization level and must exist before a persistent deployment is approved.

## Current laboratory evidence

Read-only evidence collected on 2026-07-12 confirms that the laboratory account
contains:

- `cloudops-lab-monthly`, a monthly 5 USD cost budget.
- `cloudops-zero-spend`, a monthly 1 USD early-warning budget with an actual-spend
  alert above 0.01 USD.
- Actual and forecasted budget notifications with EMAIL subscribers.
- `Default-Services-Monitor`, a service-dimensional anomaly monitor.
- Two daily anomaly subscriptions with confirmed EMAIL subscribers.
- `cloudops-daily-anomalies`, with an absolute-impact threshold of 1 USD.

Evidence:
`docs/aws-cost-governance-evidence-2026-07-12.md`.

The observed thresholds differ from the suggested production structure below.
They are documented exactly rather than treated as equivalent.

## Target controls before a persistent production deployment

- Monthly AWS cost budget for the target account.
- Actual-spend notifications at 50%, 80% and 100% of the approved amount.
- Forecasted-spend notification at 80%.
- Cost Anomaly Detection monitor and subscription.
- Confirmed email or SNS recipients.
- Cost allocation tags activated for `Project`, `Environment`, `ManagedBy`, `Owner`, `CostCenter` and `ExpirationDate`.
- Named cost owner and technical owner.
- Review of CDK bootstrap resources that remain outside normal stack destruction.
- Post-deployment cost review within 24 hours.
- Monthly review of CloudWatch, DynamoDB backup, log and notification charges.

## Suggested initial budget structure

| Scope | Period | Suggested alerts |
|---|---|---|
| Sandbox or ephemeral account | Monthly | Actual 50%, 80%, 100%; forecasted 80% |
| Persistent development account | Monthly | Actual 50%, 80%, 100%; forecasted 80% |
| Production workload | Monthly and project-specific | Actual 50%, 80%, 100%; forecasted 80%; anomaly alerts |

The approved currency and amount must come from the account owner. The repository does not invent a monetary limit.

## Important limitations

- AWS Budgets data is not real time and can be updated several hours apart.
- A budget notification does not automatically stop resources unless a separately approved budget action is configured.
- PITR, retained logs, CloudWatch dashboards, alarms and SNS delivery may generate charges.
- Deleting the application stack does not necessarily remove retained tables, retained log groups or CDK bootstrap resources.
- Cost guardrails in CI reject several expensive resource classes but do not guarantee zero cost.

## Evidence to retain

Before the first persistent deployment, capture:

1. Budget name and ARN.
2. Notification thresholds and recipients.
3. Cost anomaly monitor and subscription identifiers.
4. Activated cost allocation tags.
5. Approved monthly limit and owner.
6. Screenshot or exported configuration showing the controls are active.
7. A post-destroy inventory confirming which retained resources remain.
