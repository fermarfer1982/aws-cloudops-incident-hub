# Multi-account control matrix

This matrix maps production controls to their intended owner and enforcement layer. It is a target-state design, not evidence that the control is deployed.

## Control ownership model

| Domain | Organization owner | Workload owner | Evidence owner |
|---|---|---|---|
| Identity | Platform / identity team | Approves workload groups and roles | Security audit |
| Organization policies | Platform governance | Consumes policies; cannot modify them | Security audit |
| Central logging | Security | Ensures workload sources are enabled | Log Archive |
| Security services | Security | Remediates workload findings | Security Tooling |
| Application deployment | Platform and release engineering | Application team | Shared Services and workload account |
| Runtime operations | Workload operations | Application team | Workload account plus central logs |
| Cost governance | Finance / cloud governance | Named cost owner | Management account |
| Backup and recovery | Platform and security | Defines RTO/RPO and validates restore | Security Tooling / backup owner |
| Data governance | Data and security owners | Implements classification and retention | Production workload and Log Archive |

## Organizational controls

| ID | Control | Layer | Scope | Owner | Evidence | Status |
|---|---|---|---|---|---|---|
| ORG-001 | All AWS accounts are members of one approved Organization | AWS Organizations | Organization | Platform governance | Account inventory | Target |
| ORG-002 | Production and non-production use separate accounts | OU and account placement | Workloads | Platform governance | Organization blueprint | Target |
| ORG-003 | Management account hosts no workloads | Account policy and review | Management | Platform governance | Resource inventory | Target |
| ORG-004 | Member accounts cannot leave the Organization | SCP | Member accounts | Platform governance | SCP attachment | Example provided |
| ORG-005 | OUs are based on common controls and workload purpose | OU design | Organization | Platform governance | OU map | Target |
| ORG-006 | Suspended accounts are quarantined | SCP and account lifecycle | Suspended OU | Security and platform | Account closure record | Target |
| ORG-007 | Root access for member accounts is centrally governed | Organizations root access management | Member accounts | Security | Root credential report | Target |

## Identity controls

| ID | Control | Layer | Scope | Owner | Evidence | Status |
|---|---|---|---|---|---|---|
| IAM-001 | Workforce access uses an organization instance of IAM Identity Center | Identity Center | Organization | Identity team | Instance and assignment inventory | Target |
| IAM-002 | Assignments are group based | Identity Center | All accounts | Identity team | Group-to-permission-set export | Target |
| IAM-003 | MFA is enforced at the identity source | Identity provider | Workforce | Identity team | IdP policy | Target |
| IAM-004 | Privileged sessions have shorter duration | Permission sets | Privileged roles | Security | Permission-set configuration | Target |
| IAM-005 | Production write access is time-bound and approved | Permission sets and access process | Prod | Operations and security | Approval and CloudTrail event | Target |
| IAM-006 | No shared users or long-lived workforce access keys | IAM and policy checks | All accounts | Security | Credential report and findings | Target |
| IAM-007 | Emergency access is isolated and monitored | Break-glass process | Selected accounts | Security | Incident record and CloudTrail | Target |
| IAM-008 | Access reviews occur at least quarterly | Governance process | Organization | Identity and account owners | Signed review record | Target |

## Deployment controls

| ID | Control | Layer | Scope | Owner | Evidence | Status |
|---|---|---|---|---|---|---|
| CICD-001 | GitHub Actions authenticates using OIDC | OIDC trust policy | Dev, Stage, Prod | Platform | Workflow and role trust | Implemented for laboratory pattern |
| CICD-002 | Each environment has a dedicated deploy role | IAM roles | Workload accounts | Platform | Role inventory | Target |
| CICD-003 | OIDC trust is restricted by repository, branch, and environment | IAM trust policy | Workload accounts | Platform and security | Trust policy review | Target |
| CICD-004 | Production requires protected-environment approval | GitHub environment | Prod | Release engineering | Deployment approval log | Target |
| CICD-005 | Artifacts are built once and promoted unchanged | Artifact pipeline | Dev to Prod | Release engineering | Artifact digest | Target |
| CICD-006 | Deployment roles cannot modify organization governance | IAM policies and SCP | Workload accounts | Platform governance | IAM policy analysis | Target |
| CICD-007 | Post-deployment verification is mandatory | Workflow | Stage and Prod | Workload team | Smoke-test evidence | Laboratory pattern implemented |
| CICD-008 | Rollback criteria and runbook exist | Release process | Stage and Prod | Release engineering | Runbook and exercise evidence | Target |

## Logging and audit controls

| ID | Control | Layer | Scope | Owner | Evidence | Status |
|---|---|---|---|---|---|---|
| LOG-001 | Organization CloudTrail delivers to Log Archive | CloudTrail | Organization | Security | Trail status and S3 delivery | Target |
| LOG-002 | Workload admins cannot delete central audit logs | Bucket policy, IAM, SCP | Log Archive | Security | Access analysis | Target |
| LOG-003 | AWS Config history is centrally delivered and aggregated | AWS Config | Organization | Security / platform | Aggregator inventory | Target |
| LOG-004 | Central buckets use versioning and approved retention | S3 | Log Archive | Security | Bucket configuration | Target |
| LOG-005 | Audit access is read-only by default | Identity Center and bucket policy | Log Archive | Security | Permission-set review | Target |
| LOG-006 | Log-delivery failures generate an operational event | CloudWatch / EventBridge | Organization | Security operations | Alarm test | Target |
| LOG-007 | Retention is based on legal and incident-response requirements | Policy | Production evidence | Security and legal | Approved retention schedule | Target |

## Security controls

| ID | Control | Layer | Scope | Owner | Evidence | Status |
|---|---|---|---|---|---|---|
| SEC-101 | GuardDuty has delegated administration | GuardDuty | Organization | Security | Delegated admin and member status | Target |
| SEC-102 | Security Hub aggregates findings centrally | Security Hub | Organization | Security | Aggregator status | Target |
| SEC-103 | Inspector scans supported workloads and dependencies | Inspector | Workload accounts | Security and workload team | Findings and remediation SLA | Target |
| SEC-104 | IAM Access Analyzer evaluates external access | Access Analyzer | Organization / account | Security | Analyzer findings | Target |
| SEC-105 | API authentication and authorization are mandatory | API Gateway / application | Stage and Prod | Workload and security | Integration tests | Well-Architected P0 |
| SEC-106 | CORS uses an approved allowlist | API Gateway | Stage and Prod | Workload team | CloudFormation assertion | Well-Architected P0 |
| SEC-107 | API abuse controls and throttling are defined | API Gateway / WAF if required | Prod | Security and workload | Load and abuse tests | Well-Architected P1 |
| SEC-108 | Dependencies, secrets, and source code are scanned | GitHub security tooling | Repository | Workload and security | CI results and SBOM | Well-Architected P1 |
| SEC-109 | Data classification and retention are approved | Governance process | Prod | Data and security owners | Classification record | Well-Architected P2 |

## Reliability controls

| ID | Control | Layer | Scope | Owner | Evidence | Status |
|---|---|---|---|---|---|---|
| REL-101 | RTO and RPO are approved | Business and architecture decision | Prod | Business and workload owners | Approved document | Well-Architected P1 |
| REL-102 | DynamoDB PITR is enabled in persistent environments | DynamoDB | Stage and Prod | Workload team | CDK assertion | Well-Architected P1 |
| REL-103 | Restore is exercised and evidenced | Runbook and game day | Stage | Workload and platform | Restore report | Well-Architected P1 |
| REL-104 | DLQ redrive is controlled and idempotent | SQS and runbook | All environments | Workload operations | Redrive exercise | Partly implemented |
| REL-105 | Client retry and timeout behavior is documented | API contract | Producers | Workload team | Contract tests | Target |
| REL-106 | Regional recovery strategy is explicit | Architecture decision | Prod | Business and architecture | ADR and test plan | Well-Architected P1 |
| REL-107 | Production alarms route to responders | CloudWatch and incident tooling | Prod | Operations | Alarm delivery test | Well-Architected P1 |

## Performance controls

| ID | Control | Layer | Scope | Owner | Evidence | Status |
|---|---|---|---|---|---|---|
| PERF-101 | Production event listing uses DynamoDB Query, not Scan | Data model | Stage and Prod | Workload team | Tests and consumed-capacity evidence | Well-Architected P0 |
| PERF-102 | Operational metrics avoid synchronous full-table Scan | Aggregation design | Stage and Prod | Workload team | Architecture and load test | Well-Architected P0 |
| PERF-103 | APIs expose continuation tokens | API contract | Stage and Prod | Workload team | Contract tests | Well-Architected P2 |
| PERF-104 | Load tests define p50, p95, error, throttle, and queue-age results | Performance testing | Stage | Workload team | Test report | Well-Architected P2 |
| PERF-105 | Lambda memory, concurrency, and SQS batch are measurement based | CDK configuration | Stage and Prod | Workload team | Tuning report | Well-Architected P2 |

## Cost controls

| ID | Control | Layer | Scope | Owner | Evidence | Status |
|---|---|---|---|---|---|---|
| COST-101 | Every account has an owner and budget | AWS Budgets | Organization | Cost governance | Budget inventory | Well-Architected P1 |
| COST-102 | Cost anomaly detection has named recipients | Cost Anomaly Detection | Organization | Cost governance | Monitor and subscription | Well-Architected P1 |
| COST-103 | Mandatory cost-allocation tags are applied | Tag policies and IaC checks | Workload accounts | Cost and platform | Tag compliance report | Well-Architected P2 |
| COST-104 | Sandbox has strict limits and expiration | Budget, SCP, lifecycle | Sandbox | Platform and cost | Account policy and alerts | Target |
| COST-105 | Cost per 1,000 incidents is estimated | FinOps analysis | Stage and Prod | Workload cost owner | Versioned estimate | Well-Architected P2 |
| COST-106 | Bootstrap and orphan resources are inventoried | Inventory process | All deployment accounts | Platform | Inventory report | Target |

## Sustainability controls

| ID | Control | Layer | Scope | Owner | Evidence | Status |
|---|---|---|---|---|---|---|
| SUS-101 | Managed serverless services are preferred when they meet requirements | Architecture review | Workload | Architecture | ADR | Implemented |
| SUS-102 | ARM64 is used for compatible Lambda workloads | Lambda configuration | Workload accounts | Workload team | CDK assertion | Implemented |
| SUS-103 | Idle ephemeral environments are destroyed | Deployment workflow | Dev and test | Platform | Cleanup evidence | Implemented for laboratory pattern |
| SUS-104 | Data and log retention reflects business value | Retention policy | Organization | Data and security owners | Approved policy | Well-Architected P2 |
| SUS-105 | Efficiency KPIs are measured | Performance and cost reporting | Stage and Prod | Workload team | Incidents per invocation and GB-second | Well-Architected P2 |

## Network controls

| ID | Control | Layer | Scope | Owner | Evidence | Status |
|---|---|---|---|---|---|---|
| NET-001 | VPCs are introduced only for a documented requirement | Architecture decision | Workload accounts | Architecture | ADR | Target principle |
| NET-002 | Hybrid connectivity and shared DNS are owned centrally if introduced | Network account | Organization | Network team | Network design | Deferred |
| NET-003 | Administrative endpoints are not public | API and identity design | Prod | Security and workload | Exposure test | Target |
| NET-004 | VPC Flow Logs are enabled where VPCs exist and value justifies them | VPC | Relevant accounts | Network and security | Delivery status | Deferred |

## Evidence states

- **Implemented:** Evidence exists in the current repository or laboratory workflow.
- **Partly implemented:** A valid pattern exists, but production ownership or cross-account configuration is missing.
- **Target:** Required in the production landing zone but not deployed.
- **Well-Architected P0/P1/P2:** Linked directly to the remediation priority.
- **Deferred:** Introduced only when the relevant business or connectivity requirement exists.
