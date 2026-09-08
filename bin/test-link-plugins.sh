#!/usr/bin/env bash
set -euo pipefail
# Tests for link-plugins.sh

PASS=0
FAIL=0

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
SCRIPT="$SCRIPT_DIR/bin/link-plugins.sh"

echo "Testing link-plugins.sh..."

if [[ -x "$SCRIPT" ]]; then
  PASS=$((PASS + 1))
  echo "  ✓ link-plugins.sh exists and is executable"
else
  FAIL=$((FAIL + 1))
  echo "  ✗ link-plugins.sh exists and is executable"
fi

if head -1 "$SCRIPT" | grep -q '#!/usr/bin/env bash'; then
  PASS=$((PASS + 1))
  echo "  ✓ link-plugins.sh has correct shebang"
else
  FAIL=$((FAIL + 1))
  echo "  ✗ link-plugins.sh has correct shebang"
fi

if head -2 "$SCRIPT" | grep -q 'set -euo pipefail'; then
  PASS=$((PASS + 1))
  echo "  ✓ link-plugins.sh uses set -euo pipefail"
else
  FAIL=$((FAIL + 1))
  echo "  ✗ link-plugins.sh uses set -euo pipefail"
fi

if grep -q 'ln -sfn' "$SCRIPT"; then
  PASS=$((PASS + 1))
  echo "  ✓ link-plugins.sh uses symbolic links"
else
  FAIL=$((FAIL + 1))
  echo "  ✗ link-plugins.sh uses symbolic links"
fi

if grep -q 'common' "$SCRIPT"; then
  PASS=$((PASS + 1))
  echo "  ✓ link-plugins.sh excludes common profile"
else
  FAIL=$((FAIL + 1))
  echo "  ✗ link-plugins.sh excludes common profile"
fi

echo "Results: $PASS passed, $FAIL failed"
[[ $FAIL -eq 0 ]]
