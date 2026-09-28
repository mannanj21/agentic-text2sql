#!/usr/bin/env python3
"""Environment check script for the Agentic Text-to-SQL Analytics Platform.

Verifies all required and optional tools are installed with compatible versions.
Exit code 0 = all required tools present; exit code 1 = something missing.
"""

import os
import shutil
import subprocess
import sys

# Force UTF-8 on Windows
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
from dataclasses import dataclass


@dataclass
class Tool:
    name: str
    command: str
    args: list[str]
    required: bool
    min_version: str | None = None
    note: str = ""


TOOLS: list[Tool] = [
    Tool("Git", "git", ["--version"], required=True, min_version="2.30"),
    Tool("GitHub CLI", "gh", ["--version"], required=True, note="Needed for S0.3+"),
    Tool("Python", "python", ["--version"], required=True, min_version="3.12"),
    Tool("uv", "python", ["-m", "uv", "--version"], required=True),
    Tool("Node.js", "node", ["--version"], required=True, min_version="18"),
    Tool("npm", "npm", ["--version"], required=True),
    Tool("Docker", "docker", ["--version"], required=True, note="Needed for S0.6+"),
    Tool("Docker Compose", "docker", ["compose", "version"], required=True, note="Needed for S0.6+"),
    Tool("Ollama", "ollama", ["--version"], required=False, note="Needed for S6.1+"),
    Tool("psql", "psql", ["--version"], required=False),
]


def check_tool(tool: Tool) -> tuple[bool, str]:
    """Check if a tool is available and return (found, version_string)."""
    cmd_path = shutil.which(tool.command)
    if cmd_path is None and tool.command != "python":
        # For tools invoked via python -m, the command might not be on PATH
        if tool.args and tool.args[0] == "-m":
            pass  # Will try subprocess below
        else:
            return False, "NOT FOUND"

    try:
        # Use shell=True on Windows to resolve .cmd/.bat files (e.g., npm.cmd)
        result = subprocess.run(
            [tool.command] + tool.args,
            capture_output=True,
            text=True,
            timeout=15,
            shell=(sys.platform == "win32"),
        )
        output = (result.stdout + result.stderr).strip()
        # Extract first line with version info
        version_line = output.split("\n")[0].strip() if output else "unknown"
        return True, version_line
    except FileNotFoundError:
        return False, "NOT FOUND"
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT"
    except Exception as e:
        return False, f"ERROR: {e}"


def main() -> int:
    print("=" * 60)
    print("  Agentic Text-to-SQL Analytics Platform — Environment Check")
    print("=" * 60)
    print()

    missing_required: list[str] = []
    missing_optional: list[str] = []

    for tool in TOOLS:
        found, version = check_tool(tool)
        status = "✓" if found else ("✗" if tool.required else "○")
        req_label = "REQUIRED" if tool.required else "optional"

        note = ""
        if not found and tool.note:
            note = f"  ({tool.note})"

        print(f"  {status} {tool.name:<18} {version:<45} [{req_label}]{note}")

        if not found:
            if tool.required:
                missing_required.append(tool.name)
            else:
                missing_optional.append(tool.name)

    print()

    if missing_required:
        print(f"❌ Missing REQUIRED tools: {', '.join(missing_required)}")
        print("   Install them before proceeding.")
        print()
        return 1
    else:
        print("✅ All required tools are present.")

    if missing_optional:
        print(f"   Optional (not needed yet): {', '.join(missing_optional)}")

    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
