#!/usr/bin/env bash
set -euo pipefail
# ZeroFactory test runner — runs all tests in this directory
# Usage: bash test-runner.sh

PASS=0
FAIL=0
TOTAL=0

run_test() {
  local name="$1"
  shift
  TOTAL=$((TOTAL + 1))
  if "$@"; then
    PASS=$((PASS + 1))
    echo "  ✓ $name"
  else
    FAIL=$((FAIL + 1))
    echo "  ✗ $name"
  fi
}

# shellcheck disable=SC2046
TEST_DIR=$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")

echo "=== ZeroFactory Test Suite ==="
echo ""

# ---- merge-config.sh tests ----
echo "--- merge-config.sh ---"
bash "$TEST_DIR/test-merge-config.sh"

echo ""
echo "--- merge-jobs.sh ---"
bash "$TEST_DIR/test-merge-jobs.sh"

echo ""
echo "--- merge-soul.sh ---"
bash "$TEST_DIR/test-merge-soul.sh"

echo ""
echo "--- link-skills.sh ---"
bash "$TEST_DIR/test-link-skills.sh"

echo ""
echo "=== Results: $TOTAL total, $PASS passed, $FAIL failed ==="
if [[ $FAIL -gt 0 ]]; then
  exit 1
fi
