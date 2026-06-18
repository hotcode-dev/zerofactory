#!/usr/bin/env bash
set -euo pipefail
# Tests for merge-config.sh

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

assert_contains() {
  local file="$1" pattern="$2" label="$3"
  if grep -q "$pattern" "$file" 2>/dev/null; then
    PASS=$((PASS + 1))
    echo "  ✓ $label"
  else
    FAIL=$((FAIL + 1))
    echo "  ✗ $label (pattern '$pattern' not found in $file)"
  fi
}

# Build a minimal project structure in TEST_DIR
mkdir -p "$TEST_DIR/profiles/common" "$TEST_DIR/profiles/worker" "$TEST_DIR/bin"

# Create common config
cat > "$TEST_DIR/profiles/common/config.yaml" << 'EOF'
name: "common"
models:
  - name: default
    provider: openai
    model: gpt-4
EOF

# Create worker's custom config
cat > "$TEST_DIR/profiles/worker/config.custom.yaml" << 'EOF'
name: "worker"
tools:
  - terminal
  - web
EOF

# Copy the actual script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cp "$SCRIPT_DIR/merge-config.sh" "$TEST_DIR/bin/merge-config.sh"

echo "Testing merge-config.sh..."

# Test 1: Script exists and is executable
if [[ -x "$TEST_DIR/bin/merge-config.sh" ]]; then
  PASS=$((PASS + 1))
  echo "  ✓ merge-config.sh exists and is executable"
else
  FAIL=$((FAIL + 1))
  echo "  ✗ merge-config.sh exists and is executable"
fi

# Test 2: Script has correct shebang
if head -1 "$TEST_DIR/bin/merge-config.sh" | grep -q '#!/usr/bin/env bash'; then
  PASS=$((PASS + 1))
  echo "  ✓ merge-config.sh has correct shebang"
else
  FAIL=$((FAIL + 1))
  echo "  ✗ merge-config.sh has correct shebang"
fi

# Test 3: Script uses set -euo pipefail
if head -2 "$TEST_DIR/bin/merge-config.sh" | grep -q 'set -euo pipefail'; then
  PASS=$((PASS + 1))
  echo "  ✓ merge-config.sh uses set -euo pipefail"
else
  FAIL=$((FAIL + 1))
  echo "  ✗ merge-config.sh uses set -euo pipefail"
fi

# Test 4: merge-config.sh validates yq dependency
if grep -q 'command -v yq' "$TEST_DIR/bin/merge-config.sh"; then
  PASS=$((PASS + 1))
  echo "  ✓ merge-config.sh validates yq dependency"
else
  FAIL=$((FAIL + 1))
  echo "  ✗ merge-config.sh validates yq dependency"
fi

# Test 5: merge-config.sh handles common profile exclusion
if grep -q '"common"' "$TEST_DIR/bin/merge-config.sh" || grep -q "'common'" "$TEST_DIR/bin/merge-config.sh"; then
  PASS=$((PASS + 1))
  echo "  ✓ merge-config.sh excludes common profile"
else
  FAIL=$((FAIL + 1))
  echo "  ✗ merge-config.sh excludes common profile"
fi

# Test 6: Script actually merges config files (functional test)
# Create a simple yq-compatible setup
cd "$TEST_DIR"
bash bin/merge-config.sh > /dev/null 2>&1
if [[ -f "profiles/worker/config.yaml" ]]; then
  PASS=$((PASS + 1))
  echo "  ✓ merge-config.sh creates merged config.yaml"
else
  FAIL=$((FAIL + 1))
  echo "  ✗ merge-config.sh creates merged config.yaml"
fi

# Test 7: Merged file contains content from both common and custom
if grep -q 'gpt-4' "profiles/worker/config.yaml" 2>/dev/null && \
   grep -q 'worker' "profiles/worker/config.yaml" 2>/dev/null; then
  PASS=$((PASS + 1))
  echo "  ✓ Merged config contains both base and custom values"
else
  FAIL=$((FAIL + 1))
  echo "  ✗ Merged config contains both base and custom values"
fi

echo ""
echo "Results: $PASS passed, $FAIL failed"
