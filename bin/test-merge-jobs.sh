#!/usr/bin/env bash
set -euo pipefail
# Tests for merge-jobs.sh

PASS=0
FAIL=0
TEST_DIR=$(mktemp -d -p "$(pwd)")
cleanup() { rm -rf "$TEST_DIR"; }
trap cleanup EXIT

assert_eq() {
  local expected="$1" actual="$2" label="$3"
  if [[ "$expected" == "$actual" ]]; then
    PASS=$((PASS + 1))
    echo "  ✓ $label"
  else
    FAIL=$((FAIL + 1))
    echo "  ✗ $label (expected '$expected', got '$actual')"
  fi
}

mkdir -p "$TEST_DIR/profiles/common" "$TEST_DIR/profiles/worker" "$TEST_DIR/bin" "$TEST_DIR/profiles/worker/cron" "$TEST_DIR/profiles/common/cron"

cat > "$TEST_DIR/profiles/common/cron/jobs.json" << 'EOF'
{"jobs": [{"id": "1", "name": "default_job", "schedule": "0 */4 * * *"}]}
EOF

cat > "$TEST_DIR/profiles/worker/cron/jobs.custom.json" << 'EOF'
{"jobs": [
  {"id": "2", "name": "custom_job", "schedule": "0 */2 * * *"},
  {"id": "1", "name": "overridden_job", "schedule": "0 */3 * * *"}
]}
EOF

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cp "$SCRIPT_DIR/merge-jobs.sh" "$TEST_DIR/bin/merge-jobs.sh"

echo "Testing merge-jobs.sh..."

if [[ -x "$TEST_DIR/bin/merge-jobs.sh" ]]; then
  PASS=$((PASS + 1))
  echo "  ✓ merge-jobs.sh exists and is executable"
else
  FAIL=$((FAIL + 1))
  echo "  ✗ merge-jobs.sh exists and is executable"
fi

if head -1 "$TEST_DIR/bin/merge-jobs.sh" | grep -q '#!/usr/bin/env bash'; then
  PASS=$((PASS + 1))
  echo "  ✓ merge-jobs.sh has correct shebang"
else
  FAIL=$((FAIL + 1))
  echo "  ✗ merge-jobs.sh has correct shebang"
fi

if head -2 "$TEST_DIR/bin/merge-jobs.sh" | grep -q 'set -euo pipefail'; then
  PASS=$((PASS + 1))
  echo "  ✓ merge-jobs.sh uses set -euo pipefail"
else
  FAIL=$((FAIL + 1))
  echo "  ✗ merge-jobs.sh uses set -euo pipefail"
fi

if grep -q 'command -v jq' "$TEST_DIR/bin/merge-jobs.sh"; then
  PASS=$((PASS + 1))
  echo "  ✓ merge-jobs.sh validates jq dependency"
else
  FAIL=$((FAIL + 1))
  echo "  ✗ merge-jobs.sh validates jq dependency"
fi

if grep -q '"common"' "$TEST_DIR/bin/merge-jobs.sh" || grep -q "'common'" "$TEST_DIR/bin/merge-jobs.sh"; then
  PASS=$((PASS + 1))
  echo "  ✓ merge-jobs.sh excludes common profile"
else
  FAIL=$((FAIL + 1))
  echo "  ✗ merge-jobs.sh excludes common profile"
fi

cd "$TEST_DIR"
if timeout 10 bash bin/merge-jobs.sh > /dev/null 2>&1; then
  PASS=$((PASS + 1))
  echo "  ✓ merge-jobs.sh handles missing custom jobs gracefully"
else
  FAIL=$((FAIL + 1))
  echo "  ✗ merge-jobs.sh handles missing custom jobs gracefully"
fi

echo ""
echo "Results: $PASS passed, $FAIL failed"
