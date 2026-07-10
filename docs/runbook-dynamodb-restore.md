# Runbook: DynamoDB point-in-time restore

## Purpose

Recover the incidents and metric aggregates after accidental deletion, corruption or an unsafe application change in a persistent environment.

## Preconditions

- `persistent_environment=true` was used for the deployment.
- PITR is enabled for both DynamoDB tables.
- The operator has `dynamodb:DescribeContinuousBackups`, `dynamodb:RestoreTableToPointInTime`, `dynamodb:DescribeTable` and read permissions for validation.
- The incident commander has approved the target restore timestamp.
- No destructive change is made to the source tables during investigation.

## 1. Declare the incident

Record:

- Incident commander.
- Technical operator.
- Start time in UTC.
- Suspected corruption window.
- Current application version and stack outputs.
- Proposed restore point.

Pause deployments and any automated data migration.

## 2. Verify PITR and restorable windows

```bash
aws dynamodb describe-continuous-backups \
  --table-name cloudops-incidents

aws dynamodb describe-continuous-backups \
  --table-name cloudops-incident-metrics
```

Confirm that `PointInTimeRecoveryStatus` is `ENABLED`. Record `EarliestRestorableDateTime` and `LatestRestorableDateTime` for both tables.

## 3. Choose unique target names

```bash
export RESTORE_SUFFIX=$(date -u +%Y%m%dT%H%M%SZ)
export INCIDENTS_RESTORE="cloudops-incidents-restore-${RESTORE_SUFFIX}"
export METRICS_RESTORE="cloudops-incident-metrics-restore-${RESTORE_SUFFIX}"
```

DynamoDB PITR restores into new tables. It does not overwrite the original table.

## 4. Restore both tables

For the latest available restorable time:

```bash
aws dynamodb restore-table-to-point-in-time \
  --source-table-name cloudops-incidents \
  --target-table-name "$INCIDENTS_RESTORE" \
  --use-latest-restorable-time \
  --billing-mode-override PAY_PER_REQUEST

aws dynamodb restore-table-to-point-in-time \
  --source-table-name cloudops-incident-metrics \
  --target-table-name "$METRICS_RESTORE" \
  --use-latest-restorable-time \
  --billing-mode-override PAY_PER_REQUEST
```

For a specific approved timestamp, replace `--use-latest-restorable-time` with:

```text
--no-use-latest-restorable-time --restore-date-time <UTC_TIMESTAMP>
```

## 5. Wait for ACTIVE

```bash
aws dynamodb wait table-exists --table-name "$INCIDENTS_RESTORE"
aws dynamodb wait table-exists --table-name "$METRICS_RESTORE"

aws dynamodb describe-table --table-name "$INCIDENTS_RESTORE"
aws dynamodb describe-table --table-name "$METRICS_RESTORE"
```

Confirm both tables are `ACTIVE` and that the incidents table contains the expected four GSIs.

## 6. Validate data before cutover

Perform at least these checks:

- Retrieve known incident IDs from before the corruption window.
- Verify recent items around the selected restore point.
- Confirm status, severity, site and timestamp fields.
- Query each GSI using representative values.
- Compare aggregate counters with a sample count from incidents.
- Confirm no production Lambda points to the restored tables yet.

Do not declare recovery based only on table status.

## 7. Cutover

The current reference stack uses fixed canonical table names. Therefore a restored table requires a reviewed cutover change before application traffic can use it. Approved options are:

1. Deploy a recovery version of the stack that imports the restored table names and updates Lambda environment variables.
2. Export validated restored data and import it into newly created canonical tables during a controlled maintenance window.

Do not rename resources out of band or edit Lambda environment variables manually without recording the change and rollback plan.

## 8. Post-cutover verification

- `GET /health` succeeds.
- An authorized `GET /events` returns expected restored records.
- An authorized `GET /metrics` returns coherent counters.
- A synthetic incident completes EventBridge → SQS → Lambda → DynamoDB.
- Queue age and DLQ remain within thresholds.
- CloudWatch alarms return to `OK`.

## 9. Cleanup

Retain the original and restored tables until the incident review approves deletion. Before deletion:

- Capture table ARNs and timestamps.
- Confirm legal and retention requirements.
- Verify a second recovery path exists.
- Disable PITR only as part of an approved retirement procedure.

## Escalation and rollback

Rollback means directing the application back to the last known-good table pair and application version. If data validation fails, stop the cutover and select an earlier restore timestamp.
