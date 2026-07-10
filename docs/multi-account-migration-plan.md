# Multi-account migration plan

This plan moves AWS CloudOps Incident Hub from a local and ephemeral portfolio laboratory to a production-capable multi-account target state. It is intentionally phased so that governance exists before production data or users are introduced.

## Entry conditions

The current repository provides:

- A local Docker deployment.
- A public static GitHub Pages demo.
- AWS CDK for the serverless workload.
- EventBridge, SQS, DLQ, idempotency, CloudWatch dashboards, and alarms.
- GitHub OIDC workflows for temporary deployment and cleanup.
- A repository-based Well-Architected review and remediation backlog.

No AWS account structure, landing zone, central security service, persistent workload account, or production identity configuration is created by this plan.

## Guiding rule

**Do not create the Production account as a shortcut around unfinished governance.** Foundational logging, identity, security, cost controls, and account lifecycle must be operational first.

## Phase 0 — Approve the target state

### Objectives

- Confirm that a multi-account production landing zone is appropriate.
- Assign accountable owners.
- Decide whether to adopt AWS Control Tower or an existing enterprise landing zone.

### Actions

1. Approve the OU and account model in `governance/organization-blueprint.json`.
2. Assign platform, identity, security, network, cost, data, and workload owners.
3. Confirm primary and recovery Region constraints.
4. Approve account naming, root email, contact, support, and recovery processes.
5. Decide whether the landing zone is new or supplied by an existing organization.
6. Record applicable legal, privacy, and audit requirements.
7. Define the minimum production SLO, RTO, and RPO discovery process.

### Exit evidence

- Architecture decision approved.
- Named owners recorded.
- Landing-zone implementation path selected.
- No unresolved ambiguity about who controls the management account.

## Phase 1 — Establish the organization and identity boundary

### Objectives

- Create the organization security boundary.
- Centralize workforce access.
- Protect member account root access.

### Actions

1. Establish one AWS Organization with all features enabled.
2. Configure the management account with dedicated business contact and recovery details.
3. Enable root access management for member accounts where supported.
4. Create or connect an organization instance of IAM Identity Center.
5. Integrate the enterprise identity provider when available.
6. Create initial groups and permission sets.
7. Configure MFA and privileged session durations.
8. Document and test break-glass access.
9. Create the Security, Infrastructure, Workloads-NonProduction, Sandbox, and Suspended OUs.
10. Do not deploy application resources in the management account.

### Exit evidence

- Organization and OU inventory.
- Identity Center instance and group assignments.
- Root and break-glass procedure test.
- Management account workload inventory is empty.

## Phase 2 — Create foundational security accounts

### Objectives

- Separate audit evidence and security administration from workloads.
- Establish organization-wide visibility.

### Actions

1. Create Log Archive and Security Tooling accounts in the Security OU.
2. Establish organization CloudTrail delivery to Log Archive.
3. Configure AWS Config delivery and aggregation.
4. Apply central bucket protections, versioning, encryption, and retention.
5. Register supported delegated administrators in Security Tooling.
6. Enable GuardDuty, Security Hub, Inspector, and Access Analyzer according to scope.
7. Create security permission sets and read-only audit access.
8. Test that a workload administrator cannot delete central logs.
9. Create alerting for failed log delivery and security-service disablement.

### Exit evidence

- Organization trail status.
- Config aggregator inventory.
- Delegated administrator inventory.
- Cross-account log-protection test.
- Central finding visibility test.

## Phase 3 — Establish financial and account lifecycle governance

### Objectives

- Make every account attributable and financially observable.
- Define safe account provisioning, suspension, and closure.

### Actions

1. Define mandatory account metadata and resource tags.
2. Configure AWS Budgets for foundational and workload accounts.
3. Configure cost anomaly monitors and subscriptions.
4. Establish monthly owner review of spend and anomalies.
5. Define Sandbox budget, service limits, and expiration behavior.
6. Create account request and approval fields.
7. Define the Suspended OU quarantine process.
8. Inventory bootstrap and resources that may outlive application stacks.
9. Document who can move accounts between OUs.

### Exit evidence

- Budget and anomaly-monitor inventory.
- Tagging standard.
- Account vending checklist.
- Suspension and closure runbook.

## Phase 4 — Introduce SCPs safely

### Objectives

- Protect organization boundaries without locking out legitimate administration.

### Actions

1. Create a policy-staging OU.
2. Deploy the minimal deny-leaving-organization SCP.
3. Test normal administration, automation, service-linked roles, and break-glass paths.
4. Design and test Region restrictions with global-service exceptions.
5. Design controls protecting CloudTrail, Config, and delegated security services.
6. Add Sandbox restrictions only after representative testing.
7. Attach validated controls progressively: Sandbox, NonProduction, Production.
8. Maintain rollback instructions for every SCP change.

### Exit evidence

- Policy test report.
- Attachment map.
- Break-glass validation.
- SCP rollback exercise.

## Phase 5 — Create Shared Services and workload Dev

### Objectives

- Prove account vending, GitHub OIDC, central visibility, and workload deployment without production data.

### Actions

1. Create Shared Services and CloudOps Dev accounts.
2. Bootstrap CDK in target accounts with reviewed trust and execution policies.
3. Create the Dev deployment role restricted to the repository and GitHub environment.
4. Configure the artifact model and immutable digest capture.
5. Deploy the workload using synthetic data.
6. Confirm CloudTrail, Config, security findings, budgets, and workload telemetry.
7. Run API and asynchronous processing smoke tests.
8. Verify cleanup for ephemeral Dev deployments.
9. Confirm that the Dev role cannot modify organization governance or central logs.

### Exit evidence

- Successful OIDC role assumption.
- Dev deployment and teardown evidence.
- Central audit and security evidence.
- Permission-boundary test.
- Cost record for the test.

## Phase 6 — Remediate production blockers in Dev

### Objectives

- Close application-level Well-Architected P0 findings before creating Stage.

### Required actions

1. Add API authentication.
2. Add operation-level authorization.
3. Replace wildcard CORS with an allowlist.
4. Replace DynamoDB Scan in event listing.
5. Replace synchronous metrics Scan with scalable aggregation.
6. Add API pagination.
7. Add throttling and abuse controls.
8. Add dependency, secret, code, and SBOM checks.
9. Approve data classification and retention behavior.
10. Define client timeout, retry, and idempotency requirements.

### Exit evidence

- Well-Architected WA-001 through WA-005 closed.
- Security and data-model tests in CI.
- Synthetic load test with no full-table operational scans.

## Phase 7 — Create Stage and qualify production behavior

### Objectives

- Validate the production pattern with production-like controls and no production data.

### Actions

1. Create CloudOps Stage in Workloads-NonProduction.
2. Create a dedicated Stage OIDC deploy role.
3. Require protected-environment approval.
4. Deploy the same immutable artifact that passed Dev.
5. Enable production-like PITR, retention, alarms, and security controls.
6. Execute load tests and tune Lambda memory, concurrency, and SQS batching.
7. Execute restore tests.
8. Execute rollback tests.
9. Execute a game day covering Lambda failure, backlog, DLQ, redrive, and alarm routing.
10. Measure cost per 1,000 incidents.
11. Approve RTO, RPO, SLO, and error budget.
12. Decide single-region recovery versus multi-region design.

### Exit evidence

- Load-test report.
- Restore and rollback evidence.
- Game-day report.
- Alarm notification evidence.
- Approved SLO, RTO, RPO, and owners.
- Cost model.

## Phase 8 — Production readiness review

### Objectives

- Ensure governance and application controls are complete before creating or exposing Production.

### Gate checklist

- Well-Architected P0 findings closed.
- Well-Architected P1 findings closed or formally accepted with owner and expiration.
- Authentication, authorization, CORS, throttling, and abuse controls tested.
- No production-path DynamoDB Scan.
- RTO, RPO, SLO, and error budget approved.
- PITR and restore verified.
- Alarm routing and on-call ownership active.
- Production retention and data classification approved.
- Budgets and anomaly monitors active.
- Production permission sets and deployment-role policies reviewed.
- Central logging and security services verified.
- Regional recovery decision approved.
- Incident, release, rollback, and recovery runbooks exercised.

### Exit evidence

- Signed production-readiness record.
- Updated Well-Architected review using real account evidence.
- Security and platform approval.

## Phase 9 — Create and launch CloudOps Prod

### Objectives

- Launch Production through the approved promotion path.

### Actions

1. Create CloudOps Prod in Workloads-Production.
2. Apply the production OU controls.
3. Apply persistent data-protection and logging settings.
4. Create the dedicated Production OIDC deploy role.
5. Restrict human access to read-only operations and time-bound emergency elevation.
6. Configure protected production approvals.
7. Promote the qualified Stage artifact without rebuilding it.
8. Execute post-deployment health, processing, audit, alarm, and cost checks.
9. Record artifact digest, commit, approvers, target account, and stack outputs.
10. Begin SLO, security, and cost reporting.

### Exit evidence

- Production release record.
- Central logs and findings.
- SLO telemetry.
- Budget and anomaly monitoring.
- On-call acceptance.

## Phase 10 — Continuous governance

### Cadence

- Access review: quarterly.
- Cost review: monthly.
- Security findings: continuous with severity-based SLA.
- Restore exercise: at least annually or according to RTO/RPO criticality.
- Game day: at least twice yearly and after major architectural change.
- Well-Architected review: every six months, before major launches, and after significant incidents.
- SCP review: before each attachment expansion and after AWS service changes.
- Account inventory and owner validation: quarterly.

## Rollback principles

- SCP changes have a tested detach or prior-policy restoration path.
- Landing-zone managed resources are changed only through supported mechanisms.
- Application releases use immutable artifacts and retain the previous known-good version.
- A failed Stage qualification blocks Production promotion.
- A failed Production verification triggers rollback according to declared criteria.
- Account closure is never used as an incident-response shortcut.

## Cost warning

The migration creates persistent AWS accounts and organization-level services. It therefore cannot be considered a zero-cost activity. Pricing, free-tier eligibility, support plan, log volume, security-service coverage, backup retention, and data transfer must be evaluated before implementation.
