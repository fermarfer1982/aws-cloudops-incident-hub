# P1 reliability and operations controls

This phase adds an optional persistent deployment profile without changing the default ephemeral laboratory.

## Implemented controls

- DynamoDB point-in-time recovery for both application tables when `persistent_environment=true`.
- `Retain` deletion and replacement policies for persistent DynamoDB tables.
- Thirty-day retention and `Retain` policies for the two Lambda log groups in persistent mode.
- Optional CloudWatch alarm delivery through a dedicated SNS topic.
- Optional Amazon Q delivery to an authorized Slack channel.
- A notification-only IAM guardrail without administrative access.
- Email confirmation remains mandatory when email delivery is used.
- Initial recovery objectives, service-level objectives, restore runbook, cost-control checklist and sanitized laboratory cost-governance evidence.
- CI guardrails that verify the controls and keep ephemeral mode unchanged.

## Deployment profiles

### Ephemeral laboratory

```bash
cd infrastructure
cdk synth
```

Behavior:

- DynamoDB tables are destroyed with the stack.
- PITR is disabled.
- Lambda logs are retained for one day and destroyed with the stack.
- CloudWatch alarms have no notification action.
- No SNS topic is created.

This remains the default profile used by CI and the manual ephemeral deployment workflow.

### Persistent reference

```bash
cd infrastructure
cdk synth \
  -c persistent_environment=true \
  -c alarm_notification_email=ops@example.com
```

Behavior:

- PITR is enabled for the incidents and metrics tables.
- Tables and Lambda log groups are retained if the stack is deleted or replaced.
- Lambda logs are kept for 30 days.
- All four operational alarms publish ALARM and OK transitions to SNS.
- The email recipient must confirm the SNS subscription.

A persistent deployment can generate ongoing AWS charges and is not enabled automatically.

### ChatOps reference

The Slack profile requires both workspace and channel identifiers.

It creates one SNS topic, connects all four alarms in `ALARM` and `OK`, and configures Amazon Q with a notification-only IAM policy.

Real workspace and channel identifiers are not committed.

The infrastructure has been synthesized and tested locally. Real `ALARM` and `OK` delivery evidence is still pending.

## Recovery targets

The initial engineering targets are:

- **Incident data RPO:** 15 minutes.
- **Single-Region service RTO:** 60 minutes.
- **Operational metrics RPO:** derived from incident data and rebuildable; the incident table remains authoritative.

These are engineering targets to validate through restore exercises. They are not contractual SLAs.

## Remaining P1 gaps

- No real restore exercise has been executed in an AWS account.
- No approved service owner or on-call rotation exists.
- ChatOps IaC is validated, but real `ALARM` and `OK` delivery evidence is still pending.
- AWS Budgets and Cost Anomaly Detection are active and evidenced for the laboratory account; production tagging, budget approval and post-billing review remain pending.
- Regional recovery remains documented but untested.
- The provisional SLOs do not yet have a representative production traffic baseline.

The workload is still not production-ready.
