"""Local, read-only incident summary core.

The real adapter remains disabled unless explicitly selected with an approved model.
"""

from .client import BedrockConverseClient, DisabledBedrockClient, FakeBedrockClient
from .service import IncidentSummaryService

__all__ = [
    "BedrockConverseClient",
    "DisabledBedrockClient",
    "FakeBedrockClient",
    "IncidentSummaryService",
]
