from __future__ import annotations

import logging
import time
from decimal import Decimal
from typing import Any

import boto3
from boto3.dynamodb.conditions import Attr, Key
from boto3.dynamodb.types import TypeSerializer
from botocore.exceptions import ClientError

from .config import settings

logger = logging.getLogger(__name__)
serializer = TypeSerializer()

INCIDENT_ENTITY_TYPE = "INCIDENT"
INDEX_BY_TIME = "incidents-by-time"
INDEX_BY_SITE = "incidents-by-site"
INDEX_BY_STATUS = "incidents-by-status"
INDEX_BY_SEVERITY = "incidents-by-severity"
GLOBAL_METRIC_GROUP = "GLOBAL"
GLOBAL_METRIC_NAME = "COUNTS"
SITE_METRIC_GROUP = "SITE"


def _to_dynamodb(value: Any) -> Any:
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {key: _to_dynamodb(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_dynamodb(item) for item in value]
    return value


def _from_dynamodb(value: Any) -> Any:
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return float(value)
    if isinstance(value, dict):
        return {key: _from_dynamodb(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_from_dynamodb(item) for item in value]
    return value


def _serialize(value: Any) -> dict[str, Any]:
    return serializer.serialize(_to_dynamodb(value))


def _serialize_map(values: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {key: _serialize(value) for key, value in values.items()}


def _conditional_not_found(incident_id: str) -> ClientError:
    return ClientError(
        {
            "Error": {
                "Code": "ConditionalCheckFailedException",
                "Message": f"Incident {incident_id} was not found",
            }
        },
        "UpdateItem",
    )


class IncidentRepository:
    def __init__(self) -> None:
        kwargs: dict[str, Any] = {"region_name": settings.aws_region}
        if settings.dynamodb_endpoint:
            kwargs.update(
                endpoint_url=settings.dynamodb_endpoint,
                aws_access_key_id="local",
                aws_secret_access_key="local",
            )
        self._resource = boto3.resource("dynamodb", **kwargs)
        self._client = self._resource.meta.client
        self._table = self._resource.Table(settings.table_name)
        self._metrics_table = self._resource.Table(settings.metrics_table_name)

    def ensure_local_table(self, retries: int = 20) -> None:
        if not settings.dynamodb_endpoint:
            return

        incident_definition = {
            "TableName": settings.table_name,
            "KeySchema": [{"AttributeName": "incident_id", "KeyType": "HASH"}],
            "AttributeDefinitions": [
                {"AttributeName": "incident_id", "AttributeType": "S"},
                {"AttributeName": "entity_type", "AttributeType": "S"},
                {"AttributeName": "created_at", "AttributeType": "S"},
                {"AttributeName": "site", "AttributeType": "S"},
                {"AttributeName": "status", "AttributeType": "S"},
                {"AttributeName": "severity", "AttributeType": "S"},
            ],
            "GlobalSecondaryIndexes": [
                {
                    "IndexName": INDEX_BY_TIME,
                    "KeySchema": [
                        {"AttributeName": "entity_type", "KeyType": "HASH"},
                        {"AttributeName": "created_at", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
                {
                    "IndexName": INDEX_BY_SITE,
                    "KeySchema": [
                        {"AttributeName": "site", "KeyType": "HASH"},
                        {"AttributeName": "created_at", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
                {
                    "IndexName": INDEX_BY_STATUS,
                    "KeySchema": [
                        {"AttributeName": "status", "KeyType": "HASH"},
                        {"AttributeName": "created_at", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
                {
                    "IndexName": INDEX_BY_SEVERITY,
                    "KeySchema": [
                        {"AttributeName": "severity", "KeyType": "HASH"},
                        {"AttributeName": "created_at", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
            ],
            "BillingMode": "PAY_PER_REQUEST",
        }
        metrics_definition = {
            "TableName": settings.metrics_table_name,
            "KeySchema": [
                {"AttributeName": "metric_group", "KeyType": "HASH"},
                {"AttributeName": "metric_name", "KeyType": "RANGE"},
            ],
            "AttributeDefinitions": [
                {"AttributeName": "metric_group", "AttributeType": "S"},
                {"AttributeName": "metric_name", "AttributeType": "S"},
            ],
            "BillingMode": "PAY_PER_REQUEST",
        }

        self._ensure_local_table(self._table, incident_definition, retries)
        self._ensure_local_table(self._metrics_table, metrics_definition, retries)

    def _ensure_local_table(
        self,
        table: Any,
        definition: dict[str, Any],
        retries: int,
    ) -> None:
        for attempt in range(retries):
            try:
                table.load()
                return
            except ClientError as exc:
                code = exc.response.get("Error", {}).get("Code")
                if code == "ResourceNotFoundException":
                    try:
                        self._resource.create_table(**definition).wait_until_exists()
                        logger.info("Created local DynamoDB table %s", definition["TableName"])
                        return
                    except ClientError as create_exc:
                        create_code = create_exc.response.get("Error", {}).get("Code")
                        if create_code != "ResourceInUseException":
                            raise
                elif attempt == retries - 1:
                    raise
            except Exception:
                if attempt == retries - 1:
                    raise
            time.sleep(1)

    def put_if_absent(self, incident: dict[str, Any]) -> bool:
        stored_incident = {**incident, "entity_type": INCIDENT_ENTITY_TYPE}
        status_counter = f"status_{stored_incident['status']}"
        severity_counter = f"severity_{stored_incident['severity']}"
        updated_at = stored_incident["updated_at"]

        try:
            self._client.transact_write_items(
                TransactItems=[
                    {
                        "Put": {
                            "TableName": settings.table_name,
                            "Item": _serialize_map(stored_incident),
                            "ConditionExpression": "attribute_not_exists(incident_id)",
                        }
                    },
                    {
                        "Update": {
                            "TableName": settings.metrics_table_name,
                            "Key": _serialize_map(
                                {
                                    "metric_group": GLOBAL_METRIC_GROUP,
                                    "metric_name": GLOBAL_METRIC_NAME,
                                }
                            ),
                            "UpdateExpression": (
                                "SET #updated_at = :updated_at "
                                "ADD #total :one, #status_counter :one, #severity_counter :one"
                            ),
                            "ExpressionAttributeNames": {
                                "#updated_at": "updated_at",
                                "#total": "total",
                                "#status_counter": status_counter,
                                "#severity_counter": severity_counter,
                            },
                            "ExpressionAttributeValues": {
                                ":updated_at": _serialize(updated_at),
                                ":one": _serialize(1),
                            },
                        }
                    },
                    {
                        "Update": {
                            "TableName": settings.metrics_table_name,
                            "Key": _serialize_map(
                                {
                                    "metric_group": SITE_METRIC_GROUP,
                                    "metric_name": stored_incident["site"],
                                }
                            ),
                            "UpdateExpression": "SET #updated_at = :updated_at ADD #count :one",
                            "ExpressionAttributeNames": {
                                "#updated_at": "updated_at",
                                "#count": "count",
                            },
                            "ExpressionAttributeValues": {
                                ":updated_at": _serialize(updated_at),
                                ":one": _serialize(1),
                            },
                        }
                    },
                ]
            )
            return True
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "TransactionCanceledException":
                if self.get(stored_incident["incident_id"]) is not None:
                    return False
            raise

    def get(self, incident_id: str) -> dict[str, Any] | None:
        response = self._table.get_item(
            Key={"incident_id": incident_id},
            ConsistentRead=True,
        )
        item = response.get("Item")
        if not item:
            return None
        normalized = _from_dynamodb(item)
        normalized.pop("entity_type", None)
        return normalized

    def update_status(self, incident_id: str, status: str, updated_at: str) -> dict[str, Any]:
        for _attempt in range(3):
            current = self.get(incident_id)
            if current is None:
                raise _conditional_not_found(incident_id)

            previous_status = current["status"]
            if previous_status == status:
                response = self._table.update_item(
                    Key={"incident_id": incident_id},
                    UpdateExpression="SET updated_at = :updated_at",
                    ExpressionAttributeValues={":updated_at": updated_at},
                    ConditionExpression=Attr("incident_id").exists(),
                    ReturnValues="ALL_NEW",
                )
                normalized = _from_dynamodb(response["Attributes"])
                normalized.pop("entity_type", None)
                return normalized

            try:
                self._client.transact_write_items(
                    TransactItems=[
                        {
                            "Update": {
                                "TableName": settings.table_name,
                                "Key": _serialize_map({"incident_id": incident_id}),
                                "UpdateExpression": (
                                    "SET #status = :new_status, #updated_at = :updated_at"
                                ),
                                "ConditionExpression": (
                                    "attribute_exists(incident_id) AND #status = :previous_status"
                                ),
                                "ExpressionAttributeNames": {
                                    "#status": "status",
                                    "#updated_at": "updated_at",
                                },
                                "ExpressionAttributeValues": {
                                    ":new_status": _serialize(status),
                                    ":previous_status": _serialize(previous_status),
                                    ":updated_at": _serialize(updated_at),
                                },
                            }
                        },
                        {
                            "Update": {
                                "TableName": settings.metrics_table_name,
                                "Key": _serialize_map(
                                    {
                                        "metric_group": GLOBAL_METRIC_GROUP,
                                        "metric_name": GLOBAL_METRIC_NAME,
                                    }
                                ),
                                "UpdateExpression": (
                                    "SET #updated_at = :updated_at "
                                    "ADD #previous_counter :minus_one, #new_counter :one"
                                ),
                                "ExpressionAttributeNames": {
                                    "#updated_at": "updated_at",
                                    "#previous_counter": f"status_{previous_status}",
                                    "#new_counter": f"status_{status}",
                                },
                                "ExpressionAttributeValues": {
                                    ":updated_at": _serialize(updated_at),
                                    ":minus_one": _serialize(-1),
                                    ":one": _serialize(1),
                                },
                            }
                        },
                    ]
                )
            except ClientError as exc:
                code = exc.response.get("Error", {}).get("Code")
                if code == "TransactionCanceledException":
                    if self.get(incident_id) is None:
                        raise _conditional_not_found(incident_id) from exc
                    continue
                raise

            updated = self.get(incident_id)
            if updated is None:
                raise _conditional_not_found(incident_id)
            return updated

        raise RuntimeError(f"Concurrent status updates did not converge for {incident_id}")

    def list(
        self,
        *,
        limit: int = 100,
        severity: str | None = None,
        status: str | None = None,
        site: str | None = None,
    ) -> list[dict[str, Any]]:
        if site:
            index_name = INDEX_BY_SITE
            partition_attribute = "site"
            partition_value = site
        elif status:
            index_name = INDEX_BY_STATUS
            partition_attribute = "status"
            partition_value = status
        elif severity:
            index_name = INDEX_BY_SEVERITY
            partition_attribute = "severity"
            partition_value = severity
        else:
            index_name = INDEX_BY_TIME
            partition_attribute = "entity_type"
            partition_value = INCIDENT_ENTITY_TYPE

        filters = []
        if severity and partition_attribute != "severity":
            filters.append(Attr("severity").eq(severity))
        if status and partition_attribute != "status":
            filters.append(Attr("status").eq(status))
        if site and partition_attribute != "site":
            filters.append(Attr("site").eq(site))

        filter_expression = None
        for expression in filters:
            filter_expression = expression if filter_expression is None else filter_expression & expression

        bounded_limit = min(max(limit, 1), 500)
        kwargs: dict[str, Any] = {
            "IndexName": index_name,
            "KeyConditionExpression": Key(partition_attribute).eq(partition_value),
            "ScanIndexForward": False,
            "Limit": bounded_limit,
        }
        if filter_expression is not None:
            kwargs["FilterExpression"] = filter_expression

        items: list[dict[str, Any]] = []
        while len(items) < bounded_limit:
            response = self._table.query(**kwargs)
            for item in _from_dynamodb(response.get("Items", [])):
                item.pop("entity_type", None)
                items.append(item)
            last_key = response.get("LastEvaluatedKey")
            if not last_key:
                break
            kwargs["ExclusiveStartKey"] = last_key

        return items[:bounded_limit]

    def metrics(self) -> dict[str, Any]:
        response = self._metrics_table.get_item(
            Key={
                "metric_group": GLOBAL_METRIC_GROUP,
                "metric_name": GLOBAL_METRIC_NAME,
            },
            ConsistentRead=True,
        )
        global_metrics = _from_dynamodb(response.get("Item", {}))

        site_counts: dict[str, int] = {}
        kwargs: dict[str, Any] = {
            "KeyConditionExpression": Key("metric_group").eq(SITE_METRIC_GROUP),
            "ConsistentRead": True,
        }
        while True:
            site_response = self._metrics_table.query(**kwargs)
            for item in _from_dynamodb(site_response.get("Items", [])):
                site_counts[item["metric_name"]] = int(item.get("count", 0))
            last_key = site_response.get("LastEvaluatedKey")
            if not last_key:
                break
            kwargs["ExclusiveStartKey"] = last_key

        return {
            "total": int(global_metrics.get("total", 0)),
            "open": int(global_metrics.get("status_open", 0)),
            "investigating": int(global_metrics.get("status_investigating", 0)),
            "resolved": int(global_metrics.get("status_resolved", 0)),
            "critical": int(global_metrics.get("severity_critical", 0)),
            "warning": int(global_metrics.get("severity_warning", 0)),
            "info": int(global_metrics.get("severity_info", 0)),
            "by_site": dict(
                sorted(site_counts.items(), key=lambda item: (-item[1], item[0].lower()))
            ),
        }
