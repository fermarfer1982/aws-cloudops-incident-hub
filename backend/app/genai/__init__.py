"""Local, read-only incident summary core.

This package contains no AWS Bedrock SDK client or network integration.
"""

from .client import DisabledBedrockClient, FakeBedrockClient
from .service import IncidentSummaryService

__all__ = ["DisabledBedrockClient", "FakeBedrockClient", "IncidentSummaryService"]
