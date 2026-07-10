from __future__ import annotations

import logging
import time
from decimal import Decimal
from typing import Any

import boto3
from boto3.dynamodb.conditions import Attr
from botocore.exceptions import ClientError

from .config import settings

logger = logging.getLogger(__name__)


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
        return float(value)
    if isinstance(value, dict):
        return {key: _from_dynamodb(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_from_dynamodb(item) for item in value]
    return value


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
        self._table = self._resource.Table(settings.table_name)

    def ensure_local_table(self, retries: int = 20) -> None:
        if not settings.dynamodb_endpoint:
            return

        for attempt in range(retries):
            try:
                self._table.load()
                return
            except ClientError as exc:
                code = exc.response.get("Error", {}).get("Code")
                if code == "ResourceNotFoundException":
                    try:
                        self._resource.create_table(
                            TableName=settings.table_name,
                            KeySchema=[{"AttributeName": "incident_id", "KeyType": "HASH"}],
                            AttributeDefinitions=[
                                {"AttributeName": "incident_id", "AttributeType": "S"}
                            ],
                            BillingMode="PAY_PER_REQUEST",
                        ).wait_until_exists()
                        logger.info("Created local DynamoDB table %s", settings.table_name)
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
        try:
            self._table.put_item(
                Item=_to_dynamodb(incident),
                ConditionExpression="attribute_not_exists(incident_id)",
            )
            return True
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code == "ConditionalCheckFailedException":
                return False
            raise

    def get(self, incident_id: str) -> dict[str, Any] | None:
        response = self._table.get_item(Key={"incident_id": incident_id})
        item = response.get("Item")
        return _from_dynamodb(item) if item else None

    def update_status(self, incident_id: str, status: str, updated_at: str) -> dict[str, Any]:
        response = self._table.update_item(
            Key={"incident_id": incident_id},
            UpdateExpression="SET #status = :status, updated_at = :updated_at",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={":status": status, ":updated_at": updated_at},
            ConditionExpression=Attr("incident_id").exists(),
            ReturnValues="ALL_NEW",
        )
        return _from_dynamodb(response["Attributes"])

    def list(
        self,
        *,
        limit: int = 100,
        severity: str | None = None,
        status: str | None = None,
        site: str | None = None,
    ) -> list[dict[str, Any]]:
        filters = []
        if severity:
            filters.append(Attr("severity").eq(severity))
        if status:
            filters.append(Attr("status").eq(status))
        if site:
            filters.append(Attr("site").eq(site))

        filter_expression = None
        for expression in filters:
            filter_expression = expression if filter_expression is None else filter_expression & expression

        kwargs: dict[str, Any] = {"Limit": min(max(limit, 1), 500)}
        if filter_expression is not None:
            kwargs["FilterExpression"] = filter_expression

        items: list[dict[str, Any]] = []
        while len(items) < limit:
            response = self._table.scan(**kwargs)
            items.extend(_from_dynamodb(response.get("Items", [])))
            last_key = response.get("LastEvaluatedKey")
            if not last_key:
                break
            kwargs["ExclusiveStartKey"] = last_key

        items.sort(key=lambda item: item.get("created_at", ""), reverse=True)
        return items[:limit]
