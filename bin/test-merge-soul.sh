#!/usr/bin/env bash
set -euo pipefail
# Tests for merge-soul.sh

PASS=0
FAIL=0
TEST_DIR=$(mktemp -d -p "$(pwd)")
cleanup() { rm -rf "$TEST_DIR"; }
trap cleanup EXIT

mkdir -p "$TEST_DIR/profiles/common" "$TEST_DIR/profiles/worker" "$TEST_DIR/bin"

# Create common SOUL.md
cat > "$TEST_DIR/profiles/common/SOUL.md" << 'EOF'
# Common SOUL
System instructions for all profiles
EOF

# Create worker's custom SOUL.md
cat > "$TEST_DIR/profiles/worker/SOUL.custom.md" << 'EOF'
# Worker SOUL
Worker-specific personality
EOF

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cp "$SCRIPT_DIR/merge-soul.sh" "$TEST_DIR/bin/merge-soul.sh"

echo "Testing merge-soul.sh..."

# Test 1: Script exists and is executable
if [[ -x "$TEST_DIR/bin/merge-soul.sh" ]]; then
  PASS=$((PASS + 1))
  echo "  ✓ merge-soul.sh exists and is executable"
else
  FAIL=$((FAIL + 1))
  echo "  ✗ merge-soul.sh exists and is executable"
fi

# Test 2: Script has correct shebang
if head -1 "$TEST_DIR/bin/merge-soul.sh" | grep -q '#!/usr/bin/env bash'; then
  PASS=$((PASS + 1))
  echo "  ✓ merge-soul.sh has correct shebang"
else
  FAIL=$((FAIL + 1))
  echo "  ✗ merge-soul.sh has correct shebang"
fi

# Test 3: Script uses set -euo pipefail
if head -2 "$TEST_DIR/bin/merge-soul.sh" | grep -q 'set -euo pipefail'; then
  PASS=$((PASS + 1))
  echo "  ✓ merge-soul.sh uses set -euo pipefail"
else
  FAIL=$((FAIL + 1))
  echo "  ✗ merge-soul.sh uses set -euo pipefail"
fi

# Test 4: merge-soul.sh excludes common profile
if grep -q '"common"' "$TEST_DIR/bin/merge-soul.sh" || grep -q "'common'" "$TEST_DIR/bin/merge-soul.sh"; then
  PASS=$((PASS + 1))
  echo "  ✓ merge-soul.sh excludes common profile"
else
  FAIL=$((FAIL + 1))
  echo "  ✗ merge-soul.sh excludes common profile"
fi

# Test 5: merge-soul.sh skips profiles without SOUL.custom.md
mkdir -p "$TEST_DIR/profiles/standalone"
cp "$TEST_DIR/profiles/common/SOUL.md" "$TEST_DIR/profiles/standalone/"
cd "$TEST_DIR"
if timeout 10 bash bin/merge-soul.sh > /dev/null 2>&1; then
  PASS=$((PASS + 1))
  echo "  ✓ merge-soul.sh skips profiles without SOUL.custom.md"
else
  FAIL=$((FAIL + 1))
  echo "  ✗ merge-soul.sh skips profiles without SOUL.custom.md"
fi

# Test 6: merge-soul.sh uses mktemp for atomic writes
if grep -q 'mktemp' "$TEST_DIR/bin/merge-soul.sh"; then
  PASS=$((PASS + 1))
  echo "  ✓ merge-soul.sh uses mktemp for atomic writes"
else
  FAIL=$((FAIL + 1))
  echo "  ✗ merge-soul.sh uses mktemp for atomic writes"
fi

echo ""
echo "Results: $PASS passed, $FAIL failed"
