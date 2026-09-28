#!/usr/bin/env python3
"""Smoke test script for the Docker Compose stack.

Waits for the app-db to become healthy and runs a basic validation query.
"""

import subprocess
import sys
import time

def run(cmd: str, check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        shell=True,
        check=check,
        capture_output=capture,
        text=True
    )

def main():
    print("============================================================")
    print("  Agentic Text-to-SQL Analytics Platform — Smoke Test")
    print("============================================================")

    # 1. Bring up the stack
    print("\n> Starting Docker Compose stack...")
    run("docker compose up -d --wait")

    # 2. Wait for db to be healthy (docker compose up --wait should handle this, but let's double check)
    print("\n> Validating database connection and extensions...")
    
    # Run a simple query to verify pgvector is available
    query = "SELECT 1; CREATE EXTENSION IF NOT EXISTS vector;"
    
    # Execute query inside the container
    try:
        # PGPASSWORD=changeme is required because we didn't specify it in the command, but we'll just use the Postgres default behavior
        cmd = 'docker compose exec app-db psql -U app -d text2sql -c "SELECT 1; CREATE EXTENSION IF NOT EXISTS vector;"'
        result = run(cmd, check=True, capture=True)
        print("✅ Database is reachable and vector extension is available.")
        print(f"Output:\n{result.stdout.strip()}")
    except subprocess.CalledProcessError as e:
        print("❌ Database validation failed.")
        print(f"Error:\n{e.stderr.strip()}")
        sys.exit(1)

    print("\n✅ Smoke test passed!")
    return 0

if __name__ == "__main__":
    sys.exit(main())
