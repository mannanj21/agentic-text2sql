#!/usr/bin/env python3
"""Verify nginx distributes requests across both API replicas."""

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request


def request_replica() -> str:
    with urllib.request.urlopen("http://localhost:8000/health", timeout=10) as response:
        assert json.load(response)["status"] == "ok"
        replica = response.headers.get("X-Replica-ID")
        if replica is None:
            raise RuntimeError("Response did not include X-Replica-ID")
        return replica


def _compose(*args: str) -> None:
    subprocess.run(["docker", "compose", *args], check=True)


def test_routing() -> None:
    replicas: set[str] = set()
    for _ in range(12):
        replicas.add(request_replica())
    if replicas != {"api-1", "api-2"}:
        raise RuntimeError(f"Expected both replicas, observed: {sorted(replicas)}")
    print("Replica routing passed: api-1 and api-2 both served requests.")


def test_failover() -> None:
    """Stop api-1 briefly, prove nginx serves api-2, then restore api-1."""
    _compose("stop", "api-1")
    try:
        time.sleep(1)
        observed = {request_replica() for _ in range(4)}
        if observed != {"api-2"}:
            raise RuntimeError(f"Expected api-2 during failover, observed: {sorted(observed)}")
        print("Failover passed: nginx continued serving through api-2.")
    finally:
        _compose("start", "api-1")


def main() -> int:
    test_routing()
    if "--failover" in sys.argv:
        test_failover()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
