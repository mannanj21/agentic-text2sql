"""Mechanical checks for the specification Definition of Done."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUIRED = (
    "README.md",
    "docs/design.md",
    "docs/security.md",
    "docs/ablations.md",
    "docs/loadtest.md",
    "docs/eval/baseline-dev.md",
    "docs/eval/baseline-test.md",
    "backend/tests/security/test_enforcement.py",
)


def main() -> None:
    missing = [path for path in REQUIRED if not (ROOT / path).exists()]
    for path in REQUIRED:
        print(f"[{'OK' if path not in missing else 'MISSING'}] {path}")
    if missing:
        raise SystemExit(f"Definition-of-Done audit failed: {len(missing)} required files missing.")
    print("Definition-of-Done file audit passed. Run CI, final held-out eval, and clean-clone checks separately.")


if __name__ == "__main__":
    main()
