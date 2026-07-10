from __future__ import annotations

from .models import EventCreate, Severity


CRITICAL_TYPES = {
    "BACKUP_FAILED",
    "SERVICE_DOWN",
    "SITE_OFFLINE",
    "SECURITY_ALERT",
    "RANSOMWARE_DETECTED",
}

WARNING_TYPES = {
    "DISK_USAGE_HIGH",
    "CERTIFICATE_EXPIRING",
    "LATENCY_HIGH",
    "CPU_USAGE_HIGH",
    "MEMORY_USAGE_HIGH",
}


def classify(event: EventCreate) -> Severity:
    if event.type in CRITICAL_TYPES:
        return Severity.CRITICAL

    if event.type == "DISK_USAGE_HIGH" and event.value is not None:
        return Severity.CRITICAL if event.value >= 95 else Severity.WARNING

    if event.type == "CERTIFICATE_EXPIRING" and event.value is not None:
        return Severity.CRITICAL if event.value <= 3 else Severity.WARNING

    if event.type in WARNING_TYPES:
        return Severity.WARNING

    return Severity.INFO
