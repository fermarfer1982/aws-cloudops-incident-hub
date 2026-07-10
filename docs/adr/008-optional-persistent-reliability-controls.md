# ADR-008: Optional persistent reliability controls

- **Status:** Accepted
- **Date:** 2026-07-10

## Context

The default deployment is intentionally ephemeral: tables, logs, queues and alarms exist only for a controlled demonstration and are destroyed afterward. That profile is useful for a portfolio laboratory but does not satisfy persistent-environment requirements for data recovery or alarm delivery.

Enabling production-style controls by default would change the cost and cleanup characteristics of the project. It could also leave retained resources after an automated destroy workflow.

## Decision

Keep the ephemeral profile as the default and apply P1 controls through an explicit CDK context:

```text
persistent_environment=true
```

When enabled:

- DynamoDB PITR is enabled for the incident and metric tables.
- Both tables use `Retain` for deletion and replacement.
- Lambda log groups use 30-day retention and `Retain`.
- A data-protection mode output is added.

Alarm routing is separately opt-in:

```text
alarm_notification_email=ops@example.com
```

When provided:

- A dedicated SNS topic is created.
- An email subscription is requested.
- All four CloudWatch alarms publish both ALARM and OK state transitions.
- Delivery does not begin until the recipient confirms the subscription.

AWS Budgets and Cost Anomaly Detection remain outside the workload stack because they are account and organization governance controls.

## Consequences

### Positive

- CI and ephemeral demonstrations retain their existing cleanup behavior.
- Persistent deployments gain PITR and retained logs through Infrastructure as Code.
- Alarm delivery is explicit and testable.
- The repository clearly separates workload controls from account-level financial governance.

### Negative

- A deleted persistent stack can leave DynamoDB tables and log groups behind.
- Restoring with PITR creates new tables and still requires an approved application cutover.
- An email subscription requires manual confirmation.
- Two deployment profiles increase test and documentation complexity.

## Alternatives considered

### Enable PITR and retention for every deployment

Rejected because automated ephemeral cleanup would no longer remove all resources and could leave chargeable data behind.

### Configure budgets inside the application stack

Rejected because budgets are account-level controls, have different ownership and must normally cover more than one workload stack.

### Leave all P1 controls as documentation only

Rejected because data protection and alarm routing can be expressed and verified safely as optional IaC.

## Production gate

This ADR does not declare production readiness. A real persistent deployment still requires confirmed ownership, an executed restore test, approved RTO/RPO, validated SLOs, account-level cost controls and regional recovery decisions.
