#!/usr/bin/env bash
# Zero Factory GitHub Issue & Label Setup Script
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

python3 "$REPO_ROOT/scripts/setup_gh_issues.py" --path "$REPO_ROOT" "$@"
