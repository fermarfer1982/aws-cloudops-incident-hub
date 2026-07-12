# Workload ownership and RACI

## Status

**Approved for the repository and ephemeral laboratory scope.**

This document assigns explicit ownership for the AWS CloudOps Incident Hub
laboratory. It does not assign organizational production roles and does not make
the workload production-ready.

Approval is represented by review and merge into `main` by the repository owner.

## Scope

This ownership model applies to:

- The GitHub repository.
- The local Docker laboratory.
- GitHub Pages demonstration content.
- Manually approved ephemeral AWS deployments.
- Repository documentation, tests, guardrails and runbooks.

It does not authorize:

- A persistent production deployment.
- Processing real business or personal data.
- Unattended AWS deployments.
- Unrestricted load testing.
- A contractual SLA.
- 24x7 operational support.

## Role assignments

| Role | Assigned person | Scope | Status |
|---|---|---|---|
| Laboratory workload owner | Fernando Martínez Fernández (`fermarfer1982`) | Repository and laboratory governance | Assigned |
| Technical owner | Fernando Martínez Fernández (`fermarfer1982`) | Architecture, application and Infrastructure as Code | Assigned |
| Operations owner | Fernando Martínez Fernández (`fermarfer1982`) | Local operation, ephemeral deployment and incident triage | Assigned |
| Security owner, acting | Fernando Martínez Fernández (`fermarfer1982`) | Repository security controls and laboratory security decisions | Assigned for laboratory |
| Cost owner, acting | Fernando Martínez Fernández (`fermarfer1982`) | AWS budget review, anomaly review and deployment approval | Assigned for laboratory |
| Business and data owner | Not assigned | Business criticality, data classification and retention approval | Production blocker |
| Production service owner | Not assigned | SLA, production risk acceptance and release authority | Production blocker |
| 24x7 on-call owner | Not assigned | Continuous response and escalation | Production blocker |

The same person performs several roles because this is a single-operator portfolio
laboratory. This concentration of duties is an accepted laboratory limitation and
must not be presented as separation of duties.

## RACI legend

- **R — Responsible:** performs the work.
- **A — Accountable:** owns the decision and outcome.
- **C — Consulted:** provides review before the decision.
- **I — Informed:** receives the result or evidence.

Role names in the matrix represent responsibilities even when one person currently
performs several roles.

## RACI matrix

| Activity | Workload owner | Technical / operations | Security | Cost | Business / data |
|---|---:|---:|---:|---:|---:|
| Approve repository architecture changes | A | R | C | C | I |
| Maintain application, CDK and workflows | A | R | C | I | I |
| Approve an ephemeral AWS deployment | A | R | C | C | I |
| Approve a bounded AWS performance run | A | R | C | C | I |
| Review IAM, Cognito, secrets and dependency findings | C | R | A | I | I |
| Review AWS Budgets and cost anomalies | C | R | I | A | I |
| Triage a laboratory incident | A | R | C | I | I |
| Execute a restore or game day | A | R | C | I | C |
| Define engineering SLO, RTO and RPO proposals | A | R | C | C | C |
| Approve production SLO, RTO and RPO | C | R | C | C | A |
| Classify data and approve retention | I | R | C | I | A |
| Approve a persistent production release | C | R | C | C | A |
| Accept production security or reliability risk | C | R | A | C | A |
| Perform post-incident review | A | R | C | C | C |

Activities requiring the unassigned business/data or production service owner
remain blocked for production.

## Decision authority

The laboratory workload owner may:

- Approve repository changes through pull requests.
- Operate the local Docker environment.
- Approve a bounded ephemeral AWS deployment after explicit confirmation.
- Approve an ephemeral performance experiment after reviewing traffic and cost
  controls.
- Stop or destroy an ephemeral deployment at any time.
- Retain current technical settings when evidence does not justify tuning.
- Open and prioritize remediation items.

The laboratory workload owner may not unilaterally:

- Declare the workload production-ready.
- Approve use of real business or personal data.
- Approve a contractual SLA.
- Accept regulatory or legal risk.
- Approve a persistent production environment without the required organizational
  owners.
- Claim independent security review or separation of duties.

## Deployment approval rules

Every AWS deployment must have:

1. Explicit approval for the specific deployment.
2. Confirmed AWS account and Region.
3. Reviewed cost controls.
4. Bounded traffic where testing is involved.
5. Automatic or documented cleanup.
6. Post-run verification of resource removal.
7. Evidence that temporary approval variables were restored to their safe value.

`AWS_LOAD_TEST_APPROVED` must remain `false` outside an explicitly approved
performance run.

## Incident responsibility

For laboratory incidents, Fernando Martínez Fernández acts as incident commander
and technical responder.

The immediate priorities are:

1. Stop further deployments or traffic generation.
2. Prevent additional security, data or cost impact.
3. Preserve logs and sanitized evidence.
4. Destroy unintended ephemeral resources when safe.
5. Record the event and remediation in GitHub.
6. Review whether documentation, tests or guardrails must change.

## Escalation model

| Severity | Example | Laboratory response |
|---|---|---|
| Critical | Credential exposure, uncontrolled AWS cost, unauthorized public access or destructive data event | Stop activity immediately, revoke or disable affected access, preserve evidence and verify AWS cleanup |
| High | Deployment failure leaving resources active, repeated processing failures or messages entering the DLQ | Stop further runs, investigate logs and execute the relevant runbook |
| Medium | Functional defect with no active security or cost impact | Open an issue, reproduce locally and remediate through a pull request |
| Low | Documentation, maintainability or non-urgent improvement | Add to the backlog and prioritize normally |

There is **No 24x7 on-call** service for this laboratory. GitHub issues and pull
requests are the system of record, not a real-time paging channel.

## Production blockers

The following assignments and approvals are required before a persistent
production deployment:

- Named production service owner.
- Named business and data owner.
- Independent or organizational security owner.
- Cost owner with access to billing and forecasting.
- Operations team and on-call escalation.
- Approved SLO, RTO and RPO.
- Approved data classification and retention policy.
- Real alarm notification destination.
- Tested restore, rollback and game-day evidence.
- Formal production release and risk-acceptance process.

## Review cadence

Review this ownership model:

- Before any persistent AWS deployment.
- When any named role changes.
- After a security event, cost anomaly or game day.
- When the workload begins processing real data.
- When a production organization adopts the workload.
- At least every six months.

The next scheduled review date is **2027-01-12**, unless one of the preceding
events triggers an earlier review.

## Evidence

Current ownership evidence consists of:

- This versioned document.
- Pull-request review and merge history.
- Explicit approvals recorded before AWS deployment and performance runs.
- Automatic deployment cleanup and verification.
- The Well-Architected backlog and self-assessment.

## Well-Architected outcome

- **WA-010:** completed for the repository and laboratory reference.
- **OPS-01:** closed for laboratory ownership, but production ownership and on-call
  coverage remain open.
- Production readiness remains explicitly blocked until organizational roles are
  assigned.
