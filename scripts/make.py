#!/usr/bin/env python3
"""Cross-platform Make equivalent for Windows (PowerShell) environments.

Usage: python scripts/make.py <target> [target...]

Implements the same targets as the Makefile.
"""

import subprocess
import sys
import os

# Force UTF-8 on Windows
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BACKEND = "backend"


def run(cmd: str, cwd: str | None = None, check: bool = True) -> int:
    """Run a shell command and return the exit code."""
    print(f"\n> {cmd}")
    result = subprocess.run(cmd, shell=True, cwd=cwd)
    if check and result.returncode != 0:
        print(f"❌ Command failed with exit code {result.returncode}")
        sys.exit(result.returncode)
    return result.returncode


def uv_run(cmd: str) -> int:
    """Run a command via uv in the backend directory."""
    return run(f"python -m uv run {cmd}", cwd=BACKEND)


# ── Targets ───────────────────────────────────────────────────────

def setup():
    """Install all dependencies."""
    run("python -m uv sync --all-extras", cwd=BACKEND)
    print("✅ Backend dependencies installed")


def lint():
    """Run ruff lint + format check + mypy."""
    uv_run("ruff check app tests")
    uv_run("ruff format --check app tests")
    uv_run("mypy app")


def fmt():
    """Auto-format code."""
    uv_run("ruff check --fix app tests")
    uv_run("ruff format app tests")


def test_unit():
    """Run unit tests only."""
    uv_run("python -m pytest tests/unit -x -q --tb=short")


def test_agent():
    """Run agent tests (FakeLLM)."""
    uv_run("python -m pytest tests/agent -x -q --tb=short")


def test_integration():
    """Run integration tests (requires Postgres)."""
    uv_run("python -m pytest tests/integration -x -q --tb=short -m integration")


def test_security():
    """Run the Stage 4 security corpus and database-boundary tests."""
    uv_run("python -m pytest tests/security -x -q --tb=short")


def check():
    """Quick gate: lint + format check + types + unit tests."""
    lint()
    test_unit()


def test_all():
    """Full gate: Quick + agent + integration."""
    check()
    test_agent()
    test_integration()
    test_security()


def smoke():
    """Stack smoke test."""
    run("python scripts/smoke.py")


def up():
    """Start Docker Compose stack."""
    run("docker compose up -d --build --wait")


def down():
    """Stop Docker Compose stack."""
    run("docker compose down")


def logs():
    """Tail Docker Compose logs."""
    run("docker compose logs -f --tail=50")


def migrate():
    """Run Alembic migrations."""
    uv_run("alembic upgrade head")


def eval_run():
    """Run evaluation on dev split."""
    uv_run("python -m evaluation.run --split dev")


def fe_check():
    """Frontend checks."""
    run("npm run lint && npm run typecheck && npm run test && npm run build", cwd="frontend")


def e2e():
    """Run Playwright e2e tests."""
    run("npx playwright test", cwd="frontend")


TARGETS = {
    "setup": setup,
    "check": check,
    "lint": lint,
    "fmt": fmt,
    "test-unit": test_unit,
    "test-agent": test_agent,
    "test-integration": test_integration,
    "test-security": test_security,
    "test-all": test_all,
    "smoke": smoke,
    "up": up,
    "down": down,
    "logs": logs,
    "migrate": migrate,
    "eval": eval_run,
    "fe-check": fe_check,
    "e2e": e2e,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        print("Available targets:")
        for name, fn in TARGETS.items():
            print(f"  {name:<20} {fn.__doc__ or ''}")
        return

    # Change to repo root
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(repo_root)

    for target in sys.argv[1:]:
        if target not in TARGETS:
            print(f"❌ Unknown target: {target}")
            print(f"   Available: {', '.join(TARGETS.keys())}")
            sys.exit(1)
        print(f"\n{'='*60}")
        print(f"  Running: {target}")
        print(f"{'='*60}")
        TARGETS[target]()

    print(f"\n✅ All targets completed successfully.")


if __name__ == "__main__":
    main()
