# AWS Well-Architected Review

## Review metadata

- **Workload:** AWS CloudOps Incident Hub
- **Review type:** Repository-based self-assessment
- **Review date:** 2026-07-13
- **Reviewer:** Fernando Martínez Fernández
- **Framework:** AWS Well-Architected Framework, six pillars
- **Environment assessed:** Local zero-cost laboratory plus validated ephemeral AWS performance and WA-014 ChatOps deployments
- **Production readiness:** Not production-ready

> This document is a technical self-assessment, not an AWS Well-Architected Tool review and not an external audit. Findings are based on evidence versioned in this repository. A control marked as completed in the reference implementation still requires deployment evidence and operational validation before production use.

## Scope and assumptions

The workload receives infrastructure incidents and processes them through API Gateway, Lambda, EventBridge, SQS, a Dead Letter Queue, DynamoDB and CloudWatch. The AWS reference now includes Amazon Cognito, JWT route scopes, explicit CORS origins, query-oriented DynamoDB indexes and transactional metric aggregates.

The local implementation uses Docker, FastAPI and DynamoDB Local. Local mode deliberately remains unauthenticated inside the trusted development network. The public GitHub Pages dashboard contains demonstration data only.

No persistent production traffic profile, RTO, RPO, SLO, compliance regime, data classification or formal ownership model has been approved. A real AWS deployment may incur charges.

## Rating model

| Rating | Meaning |
|---|---|
| Low risk | Controls are appropriate for the current scope; minor improvements remain. |
| Medium risk | Important controls exist, but one or more material gaps remain. |
| High risk | A production launch would expose an unacceptable failure, security or governance risk. |
| Not assessed | Evidence or requirements are insufficient for a defensible conclusion. |

## Executive summary

| Pillar | Current rating | Main strength | Main risk |
|---|---|---|---|
| Operational excellence | Medium | IaC, CI, runbooks, laboratory ownership, validated laboratory alert routing and cleanup | No approved production SLO, on-call or organizational alert-routing process |
| Security | Medium for production reference | Cognito JWT scopes, OIDC federation, explicit CORS, throttling and supply-chain automation | Data classification, broader abuse protection, operational triage and durable release evidence remain incomplete |
| Reliability | Medium | EventBridge, SQS, DLQ, retries, idempotency and alarms | No approved RTO/RPO, restore test or regional recovery strategy |
| Performance efficiency | Medium | Query pagination, incremental metrics, ARM64 and validated local/AWS baselines | No sustained-capacity test or comparative tuning |
| Cost optimization | Low for laboratory / Medium for production | Ephemeral lifecycle, two budgets and anomaly detection evidence | No production unit economics, tag evidence or approved production budget |
| Sustainability | Low for laboratory / Medium for production | Ephemeral resources, managed services and query access patterns | No utilization baseline or sustainability KPI |

### Overall conclusion

WA-001 through WA-005 are closed in the reference implementation: the cloud API is authenticated and scope-authorized, CORS is explicit, operational listings use DynamoDB Query and metrics are materialized transactionally. WA-014 also validates real `ALARM` and `OK` delivery through SNS, Amazon Q Developer and Slack for the laboratory. This is a **validated laboratory reference architecture**, but it remains **not production-ready** because approved production SLOs, organizational ownership and on-call coverage, tested restore, organizational alert routing, durable release evidence, data governance, broader abuse protection and sustained-capacity evidence are still missing.

---

# 1. Operational excellence

## Evidence

- AWS CDK defines the cloud architecture.
- GitHub Actions runs linting, tests, CDK synthesis and all guardrails.
- Deployment uses GitHub OIDC, explicit confirmation, smoke tests and automatic destroy.
- CloudWatch dashboards, alarms, runbooks, ADRs and temporary evidence are versioned.
- A named laboratory workload owner, role assignments, decision rights, escalation
  model and RACI matrix are versioned in `docs/workload-ownership.md`.
- WA-014 records real `ALARM` and `OK` delivery to an authorized laboratory Slack
  channel and verified removal of the ephemeral stack.

## Risks and gaps

| ID | Risk | Severity | Status |
|---|---|---|---|
| OPS-01 | No approved service owner, escalation path or on-call responsibility | High | Closed for laboratory ownership; production roles and on-call remain open |
| OPS-02 | No SLO, error budget, availability target or latency objective | High | Open |
| OPS-03 | Alarm routing and responder integration | Medium | Closed for laboratory routing by WA-014; production on-call, ownership and organizational receiver remain open |
| OPS-04 | No game-day or failure-injection evidence | Medium | Open |
| OPS-05 | Release and rollback procedure has not been exercised | Medium | Runbook documented for WA-020; release creation and rollback remain unexercised |

## Recommended actions

Assign organizational production owners, approve measurable SLOs, connect alarms to an approved production receiver and on-call process, execute game days, and exercise the documented release/rollback criteria.

## Pillar rating

**Medium risk.** Laboratory accountability and alert routing are validated, but production ownership, on-call coverage, approved outcomes and organizational alert routing remain incomplete.

---

# 2. Security

## Evidence

- GitHub Actions uses OIDC and temporary STS credentials.
- API Gateway uses a Cognito JWT authorizer.
- Custom scopes separate read, write and manage operations.
- Only `GET /health` is public in AWS.
- CORS uses an explicit allowlist.
- DynamoDB and SQS use managed encryption, and Lambda policies exclude `dynamodb:Scan`.
- API Gateway has explicit throttling validated by a conservative laboratory baseline.
- Dependabot, CodeQL, a repository secret-pattern guardrail and an SPDX JSON SBOM
  workflow are implemented.

## Risks and gaps

| ID | Risk | Severity | Status |
|---|---|---|---|
| SEC-01 | API Gateway endpoint has no authentication or authorization | Critical | Closed in reference implementation |
| SEC-02 | CORS allows every origin | High | Closed in reference implementation |
| SEC-03 | WAF decision and abuse protection remain incomplete | High | Throttling defined and validated at 5 requests/s; broader protection open |
| SEC-04 | No formal data classification, retention policy or privacy assessment | High | Open |
| SEC-05 | Supply-chain controls lack complete operational and release evidence | Medium | CodeQL, Dependabot, the secret guardrail and SBOM workflow are implemented; repository settings, triage and durable release-bound SBOM evidence remain partial |
| SEC-06 | Effective CDK bootstrap-role permissions require separate review | Medium | Open |
| SEC-07 | Central CloudTrail, GuardDuty and Security Hub remain target-state controls | Medium | Deferred to landing zone implementation |

## Recommended actions

Validate federation and client separation in the target environment, validate broader abuse controls, define data governance, confirm repository security settings and triage, and bind a verified SBOM to the future release.

## Pillar rating

**Medium risk for the production reference.** Authentication, authorization and CORS blockers are closed in code, but production identity operations, abuse protection and governance evidence are not yet complete.

---

# 3. Reliability

## Evidence

- EventBridge decouples ingestion from processing.
- SQS provides durable buffering, retries and partial batch failure handling.
- A DLQ retains poison messages.
- Conditional writes and deterministic identifiers provide idempotency.
- Transactional counters keep incident and metric changes consistent.
- Queue-age, Lambda-error and DLQ alarms are defined.
- RTO and RPO are documented as engineering targets for a future persistent
  environment, and optional PITR is expressed in IaC.
- WA-014 validates real laboratory `ALARM` and `OK` delivery through the optional
  ChatOps path.

## Risks and gaps

| ID | Risk | Severity | Status |
|---|---|---|---|
| REL-01 | RTO and RPO lack approval and exercise evidence | High | Engineering targets are defined; organizational approval and a recovery exercise remain open |
| REL-02 | DynamoDB PITR and backup policy are not enabled | High | Accepted for ephemeral laboratory only |
| REL-03 | Restore procedures have not been tested | High | Open |
| REL-04 | Architecture is single-region with no approved recovery strategy | Medium | Open |
| REL-05 | Client timeout, retry and backoff behavior are not documented | Medium | Open |
| REL-06 | Poison-message and redrive integration evidence is incomplete | Medium | Open |
| REL-07 | Alarm notifications lack a production responder path | Medium | Real `ALARM`/`OK` delivery validated for WA-014 laboratory routing; production receiver and on-call process remain open |

## Recommended actions

Approve the proposed RTO/RPO, enable PITR for persistent environments, test restore and regional recovery, and execute failure scenarios with the production responder path.

## Pillar rating

**Medium risk.** Failure isolation and laboratory notification delivery are strong, but recovery objectives are not approved and restore evidence is absent.

---

# 4. Performance efficiency

## Evidence

- Lambda uses Python 3.13 on ARM64 with bounded 256 MB memory.
- SQS processing uses batch size 10, a five-second batching window and maximum concurrency two.
- The incidents table has GSIs for time, site, status and severity.
- `GET /events` uses DynamoDB Query and opaque continuation-token pagination.
- Local pagination validation traversed 365 unique IDs with zero duplicates.
- Metrics are maintained as transactional incremental aggregates.
- The controlled AWS baseline completed 152 requests at 5.01 requests/s with 0% errors.
- API and processor Lambdas recorded zero errors and zero throttles.
- Two asynchronous SQS messages were sent, received and deleted.

## Risks and gaps

| ID | Risk | Severity | Status |
|---|---|---|---|
| PERF-01 | `GET /events` uses DynamoDB Scan and in-memory filtering | High at scale | Closed in reference implementation |
| PERF-02 | Metrics scan and aggregate incident records synchronously | High at scale | Closed in reference implementation |
| PERF-03 | No load test, throughput objective or representative traffic model | High | Closed for the controlled laboratory baseline; sustained production profile remains open |
| PERF-04 | API throttling and SQS maximum concurrency may constrain larger bursts | Medium | Intentional laboratory guardrails; no throttling observed at 5 requests/s |
| PERF-05 | Memory, timeout and batch settings require comparative tuning for larger targets | Medium | Current settings retained from AWS evidence; comparative run open |
| PERF-06 | No continuation-token pagination contract is exposed | Medium | Closed and validated locally |

## Recommended actions

Repeat the AWS test with a longer or higher approved traffic profile only when a business objective requires it. Any tuning proposal must compare one controlled parameter, inspect throttles and backlog, and record cost implications.

## Pillar rating

**Medium risk.** Query access, pagination and a conservative AWS baseline are validated, but sustained capacity, production data volume and comparative tuning remain unmeasured.

---

# 5. Cost optimization

## Evidence

- Local mode and GitHub Pages do not require AWS runtime resources.
- AWS deployment is manual, temporary and automatically destroyed.
- Static guardrails reject high-risk fixed-cost resources.
- DynamoDB uses on-demand capacity and Lambda compute is bounded.
- The laboratory account has two monthly budgets with actual and forecasted
  notifications.
- A service-dimensional anomaly monitor and two daily anomaly subscriptions are
  configured.
- Sanitized evidence is versioned in
  `docs/aws-cost-governance-evidence-2026-07-12.md`.

## Risks and gaps

| ID | Risk | Severity | Status |
|---|---|---|---|
| COST-01 | No AWS Budget, anomaly monitor or billing alarm is defined | High before real deployment | Closed for laboratory budgets and anomaly detection; production approval remains open |
| COST-02 | Cost allocation tags are incomplete | Medium | Open |
| COST-03 | No cost-per-incident model exists | Medium | Open |
| COST-04 | CDK bootstrap resources may remain after stack destruction | Medium | Documented |
| COST-05 | CloudWatch and Cognito usage may incur charges in a real account | Medium | Documented |
| COST-06 | Emergency cleanup depends on the federated role and GitHub availability | Medium | Accepted risk |

## Recommended actions

Retain the laboratory budget and anomaly evidence, complete production tagging, approve a production-specific budget, estimate cost per 1,000 incidents and inventory orphaned resources.

## Pillar rating

**Low risk for the laboratory and medium risk for production.** Laboratory budgets and anomaly alerts are evidenced, but production tagging, unit economics, forecasting and financial approval remain incomplete.

---

# 6. Sustainability

## Evidence

- The workload is not kept running in AWS by default.
- Managed serverless services scale with demand.
- Lambda uses ARM64 and SQS batching.
- Query-based access and incremental metrics avoid repeated table scans.
- Log retention is short in the ephemeral environment.

## Risks and gaps

| ID | Risk | Severity | Status |
|---|---|---|---|
| SUS-01 | No utilization, energy or sustainability KPI is measured | Medium | Open |
| SUS-02 | No retention policy linked to business value exists | Medium | Open |
| SUS-03 | No regional sustainability criterion has been evaluated | Low | Open |
| SUS-04 | Inefficient DynamoDB scans would waste read capacity at scale | Medium | Closed in reference implementation |
| SUS-05 | Repeated full deployments consume build and cloud resources | Low | Mitigated by manual execution |

## Recommended actions

Measure useful work per Lambda invocation and GB-second, define retention by business value and evaluate region using latency, regulation, resilience and sustainability together.

## Pillar rating

**Low risk for the laboratory and medium risk for production.** The design avoids idle capacity and table scans, but no quantitative sustainability target exists.

---

# Cross-pillar priorities

## Production blockers

1. **SEC-01 / SEC-02:** Closed in reference; validate Cognito federation, scopes and CORS in the target environment.
2. **PERF-01 / PERF-02 / PERF-03 / PERF-06:** Closed for the controlled reference baseline; repeat only for a higher production traffic objective.
3. **REL-01 / REL-02 / REL-03:** Approve the proposed RTO/RPO, enable recovery controls and test restore.
4. **OPS-01 / OPS-02:** Assign ownership and approve SLOs.
5. **COST-01:** Laboratory financial controls are evidenced; approve production budgets, tagging and unit economics.
6. **SEC-03 / SEC-04 / SEC-05:** Validate broader abuse protection, define data governance, confirm operational security settings and triage, and publish durable release-bound SBOM evidence.

## Accepted laboratory risks

The following choices are acceptable only because this is a short-lived portfolio laboratory:

- Local Docker mode remains unauthenticated inside the trusted operator network.
- DynamoDB tables are deleted with the ephemeral stack.
- No point-in-time recovery.
- One-day log retention.
- No alarm notification actions in the default ephemeral profile; the separately
  enabled WA-014 ChatOps profile has validated laboratory delivery.
- Conservative SQS event-source maximum concurrency of two.
- The 30-second, 5 requests/s baseline does not prove sustained or peak production capacity.

## Review cadence

Repeat this review before real users or data, after identity or recovery changes, when a persistent environment is created, after material traffic changes, after an incident or game day, and at least every six months.

## Evidence index

- `backend/app/repository.py`
- `infrastructure/cloudops_infra/stack.py`
- `.github/workflows/validate.yml`
- `.github/workflows/deploy-ephemeral.yml`
- `.github/workflows/aws-performance-ephemeral.yml`
- `scripts/run_load_test.py`
- `scripts/collect_aws_performance_evidence.py`
- `docs/performance-baseline-local-2026-07-10.md`
- `docs/performance-baseline-aws-2026-07-12.md`
- `docs/workload-ownership.md`
- `docs/aws-cost-governance-evidence-2026-07-12.md`
- `docs/evidence/aws-cost-governance-2026-07-12.json`
- `docs/wa-014-chatops-evidence-2026-07-13.md`
- `docs/evidence/wa-014/`
- `docs/p1-operational-security-supply-chain.md`
- `.github/workflows/sbom.yml`
- `docs/adr/012-amazon-q-slack-chatops.md`
- `scripts/check_p0_controls.py`
- `docs/p0-production-controls.md`
- `docs/observability.md`
- `docs/runbook-dlq.md`
- `docs/adr/`

## Reference

This review uses the six pillars of the AWS Well-Architected Framework: operational excellence, security, reliability, performance efficiency, cost optimization, and sustainability.
