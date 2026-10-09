#!/usr/bin/env python3
"""Verify nginx distributes requests across both API replicas."""

from __future__ import annotations

import json
import sys
import urllib.request


def main() -> int:
    replicas: set[str] = set()
    for _ in range(12):
        with urllib.request.urlopen("http://localhost:8000/health", timeout=10) as response:
            assert json.load(response)["status"] == "ok"
            replica = response.headers.get("X-Replica-ID")
            if replica:
                replicas.add(replica)
    if replicas != {"api-1", "api-2"}:
        print(f"Expected both replicas, observed: {sorted(replicas)}", file=sys.stderr)
        return 1
    print("Replica routing passed: api-1 and api-2 both served requests.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
