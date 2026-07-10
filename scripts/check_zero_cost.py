#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

FORBIDDEN_TYPES = {
    "AWS::EC2::NatGateway",
    "AWS::EC2::Instance",
    "AWS::RDS::DBInstance",
    "AWS::RDS::DBCluster",
    "AWS::ElasticLoadBalancingV2::LoadBalancer",
    "AWS::EKS::Cluster",
    "AWS::OpenSearchService::Domain",
    "AWS::ElastiCache::CacheCluster",
    "AWS::ElastiCache::ReplicationGroup",
}


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: check_zero_cost.py <cloudformation-template.json>")
        return 2

    template_path = Path(sys.argv[1])
    template = json.loads(template_path.read_text(encoding="utf-8"))
    resources = template.get("Resources", {})
    found = sorted(
        {resource.get("Type") for resource in resources.values()} & FORBIDDEN_TYPES
    )
    if found:
        print("Forbidden cost-risk resources detected:")
        for resource_type in found:
            print(f"- {resource_type}")
        return 1

    print(f"OK: {len(resources)} resources checked; no forbidden cost-risk types found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
