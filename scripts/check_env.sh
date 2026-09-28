#!/usr/bin/env bash
# Environment check script — exits non-zero if any required tool is missing.
# Used in CI and documented in README.

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

MISSING=0

check() {
    local name="$1"
    local cmd="$2"
    local required="$3"

    if command -v "$cmd" &>/dev/null; then
        local version
        version=$("$cmd" --version 2>&1 | head -1)
        printf "  ${GREEN}✓${NC} %-18s %s\n" "$name" "$version"
    else
        if [ "$required" = "yes" ]; then
            printf "  ${RED}✗${NC} %-18s NOT FOUND [REQUIRED]\n" "$name"
            MISSING=1
        else
            printf "  ${YELLOW}○${NC} %-18s NOT FOUND [optional]\n" "$name"
        fi
    fi
}

echo "============================================================"
echo "  Agentic Text-to-SQL Analytics Platform — Environment Check"
echo "============================================================"
echo

check "Git"              git     yes
check "GitHub CLI"       gh      yes
check "Python"           python3 yes
check "uv"              uv      yes
check "Node.js"         node    yes
check "npm"             npm     yes
check "Docker"          docker  yes
check "Ollama"          ollama  no
check "psql"            psql    no

# Docker Compose (special: subcommand)
if docker compose version &>/dev/null; then
    version=$(docker compose version 2>&1 | head -1)
    printf "  ${GREEN}✓${NC} %-18s %s\n" "Docker Compose" "$version"
else
    printf "  ${RED}✗${NC} %-18s NOT FOUND [REQUIRED]\n" "Docker Compose"
    MISSING=1
fi

# Make
if command -v make &>/dev/null; then
    version=$(make --version 2>&1 | head -1)
    printf "  ${GREEN}✓${NC} %-18s %s\n" "Make" "$version"
else
    printf "  ${YELLOW}○${NC} %-18s NOT FOUND [optional on Windows]\n" "Make"
fi

echo
if [ "$MISSING" -eq 1 ]; then
    echo -e "${RED}❌ Missing required tools. Install them before proceeding.${NC}"
    exit 1
else
    echo -e "${GREEN}✅ All required tools are present.${NC}"
fi
