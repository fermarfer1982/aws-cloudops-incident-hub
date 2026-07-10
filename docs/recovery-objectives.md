# Recovery objectives

## Scope

These objectives apply to a future persistent single-Region deployment of AWS CloudOps Incident Hub. They do not apply to the default ephemeral demonstration stack.

## Proposed objectives

| Capability | Target | Rationale |
|---|---:|---|
| Incident records RPO | 15 minutes | DynamoDB PITR provides continuous backups; the target includes detection and operator decision time. |
| Incident service RTO | 60 minutes | Allows time to identify corruption, restore both tables to new names, validate data and perform an approved cutover. |
| Metrics availability RTO | 120 minutes | Metrics are derived operational data and can be rebuilt after the authoritative incidents table is available. |
| Queue processing recovery | 30 minutes | SQS buffers transient processor failures and the DLQ preserves poison messages for investigation. |
| Regional disaster RTO/RPO | Not approved | A second Region and data replication strategy have not been selected. |

## Assumptions

- Incident records are the authoritative business data.
- Aggregate metrics can be reconstructed and are not an authoritative ledger.
- The first production design is single-Region.
- Restores create new DynamoDB tables; they do not overwrite the source tables.
- A cutover requires an explicit infrastructure change and validation.
- Recovery permissions and a functioning AWS control plane remain available.

## Validation criteria

The RTO and RPO targets are considered validated only when a game day records:

1. The selected restore point.
2. The earliest and latest restorable timestamps.
3. Start and completion timestamps for each restored table.
4. Data-integrity checks for representative incidents.
5. Application cutover and rollback evidence.
6. Total measured recovery time.
7. Estimated data loss relative to the selected restore point.
8. Lessons learned and follow-up actions.

Until such evidence exists, these values remain engineering targets rather than an SLA.
