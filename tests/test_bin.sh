#!/usr/bin/env bash
set -euo pipefail
# ZeroFactory — comprehensive tests for bin/merge-*.sh scripts
# Usage: bash tests/test_bin.sh

PASS=0
FAIL=0
TOTAL=0
TEST_DIR_BASE=$(mktemp -d)
TEST_DIR="$TEST_DIR_BASE/test_bin"
BIN_DIR="$TEST_DIR/bin"
PROFILES_DIR="$TEST_DIR/profiles"
COMMON_DIR="$PROFILES_DIR/common"
WORKER_DIR="$PROFILES_DIR/worker"

cleanup() { rm -rf "$TEST_DIR_BASE"; }
trap cleanup EXIT

# Copy the actual scripts into the test environment before each test section
copy_scripts() {
  cp ~/git/hotcode-dev/zerofactory/bin/merge-config.sh "$BIN_DIR/merge-config.sh"
  cp ~/git/hotcode-dev/zerofactory/bin/merge-jobs.sh "$BIN_DIR/merge-jobs.sh"
  cp ~/git/hotcode-dev/zerofactory/bin/merge-soul.sh "$BIN_DIR/merge-soul.sh"
  cp ~/git/hotcode-dev/zerofactory/bin/link-skills.sh "$BIN_DIR/link-skills.sh"
  cp ~/git/hotcode-dev/zerofactory/bin/link-plugins.sh "$BIN_DIR/link-plugins.sh"
}

assert_exit() {
  local script="$1" expected="$2" label="$3"
  set +e
  "$script" >/dev/null 2>&1
  local actual=$?
  set -e
  TOTAL=$((TOTAL + 1))
  if [[ "$actual" -eq "$expected" ]]; then
    PASS=$((PASS + 1))
    echo "  ✓ $label"
  else
    FAIL=$((FAIL + 1))
    echo "  ✗ $label (expected exit $expected, got $actual)"
  fi
}

assert_contains() {
  local file="$1" pattern="$2" label="$3"
  TOTAL=$((TOTAL + 1))
  if grep -q "$pattern" "$file" 2>/dev/null; then
    PASS=$((PASS + 1))
    echo "  ✓ $label"
  else
    FAIL=$((FAIL + 1))
    echo "  ✗ $label (pattern '$pattern' not found in $file)"
  fi
}

assert_file_exists() {
  local file="$1" label="$2"
  TOTAL=$((TOTAL + 1))
  if [[ -f "$file" ]]; then
    PASS=$((PASS + 1))
    echo "  ✓ $label"
  else
    FAIL=$((FAIL + 1))
    echo "  ✗ $label (file not found: $file)"
  fi
}

assert_file_not_exists() {
  local file="$1" label="$2"
  TOTAL=$((TOTAL + 1))
  if [[ ! -f "$file" ]]; then
    PASS=$((PASS + 1))
    echo "  ✓ $label"
  else
    FAIL=$((FAIL + 1))
    echo "  ✗ $label (file should not exist: $file)"
  fi
}

# === merge-config.sh ===
echo "=== merge-config.sh ==="

# --- 1. Happy path: valid common + worker config ---
mkdir -p "$COMMON_DIR" "$WORKER_DIR" "$BIN_DIR"
copy_scripts
cat > "$COMMON_DIR/config.yaml" <<'EOF'
name: "common"
models:
  - name: default
    provider: openai
    model: gpt-4
tools:
  - web
  - browser
EOF
cat > "$WORKER_DIR/config.custom.yaml" <<'EOF'
name: "worker"
tools:
  - terminal
  - web
EOF
rm -f "$WORKER_DIR/config.yaml"
assert_exit "$BIN_DIR/merge-config.sh" 0 "merge-config.sh succeeds with valid inputs"

# --- 2. Merged config contains content from both ---
assert_contains "$WORKER_DIR/config.yaml" '"common"' "merged config contains common name"
assert_contains "$WORKER_DIR/config.yaml" '"worker"' "merged config contains custom name"
assert_contains "$WORKER_DIR/config.yaml" '"terminal"' "merged config contains custom tool"

# --- 3. Custom overrides common on key conflict ---
mkdir -p "$COMMON_DIR" "$WORKER_DIR" "$BIN_DIR"
cat > "$COMMON_DIR/config.yaml" <<'EOF'
name: "common"
tools:
  - web
  - browser
  - terminal
EOF
cat > "$WORKER_DIR/config.custom.yaml" <<'EOF'
name: "worker"
tools:
  - terminal
  - web
EOF
rm -f "$WORKER_DIR/config.yaml"
assert_exit "$BIN_DIR/merge-config.sh" 0 "merge-config.sh handles key conflicts"

# --- 4. Missing common config exits 1 ---
mkdir -p "$COMMON_DIR" "$WORKER_DIR" "$BIN_DIR"
rm -f "$COMMON_DIR/config.yaml"
cat > "$WORKER_DIR/config.custom.yaml" <<'EOF'
name: "worker"
tools:
  - terminal
EOF
rm -f "$WORKER_DIR/config.yaml"
assert_exit "$BIN_DIR/merge-config.sh" 1 "merge-config.sh exits 1 when common config is missing"

# --- 5. Profile without custom config is skipped ---
mkdir -p "$COMMON_DIR" "$WORKER_DIR" "$PROFILES_DIR/standalone" "$BIN_DIR"
cat > "$COMMON_DIR/config.yaml" <<'EOF'
name: "common"
tools:
  - web
EOF
cat > "$WORKER_DIR/config.custom.yaml" <<'EOF'
name: "worker"
tools:
  - terminal
EOF
# standalone has no config.custom.yaml
rm -f "$WORKER_DIR/config.yaml" "$PROFILES_DIR/standalone/config.yaml"
assert_exit "$BIN_DIR/merge-config.sh" 0 "merge-config.sh skips profiles without custom"
assert_file_not_exists "$PROFILES_DIR/standalone/config.yaml" "standalone has no merged config"

# --- 6. Missing profile custom exits 1 ---
mkdir -p "$COMMON_DIR" "$WORKER_DIR" "$BIN_DIR"
cat > "$COMMON_DIR/config.yaml" <<'EOF'
name: "common"
tools:
  - web
EOF
rm -f "$WORKER_DIR/config.custom.yaml" "$WORKER_DIR/config.yaml"
assert_exit "$BIN_DIR/merge-config.sh" 1 "merge-config.sh exits 1 when profile custom config is missing"

# --- 7. Corrupt YAML ---
mkdir -p "$COMMON_DIR" "$WORKER_DIR" "$BIN_DIR"
cat > "$COMMON_DIR/config.yaml" <<'EOF'
name: "common"
tools:
  - web
EOF
cat > "$WORKER_DIR/config.custom.yaml" <<'EOF'
name: "worker"
broken yaml: [
EOF
rm -f "$WORKER_DIR/config.yaml"
assert_exit "$BIN_DIR/merge-config.sh" 0 "merge-config.sh handles corrupt YAML"

# --- 8. No profiles found (only common) ---
mkdir -p "$COMMON_DIR" "$BIN_DIR"
cat > "$COMMON_DIR/config.yaml" <<'EOF'
name: "common"
tools:
  - web
EOF
rm -f "$WORKER_DIR/config.yaml"
assert_exit "$BIN_DIR/merge-config.sh" 0 "merge-config.sh exits 1 when no profiles found"

echo ""

# === merge-jobs.sh ===
echo "=== merge-jobs.sh ==="

# --- 1. Happy path ---
mkdir -p "$COMMON_DIR" "$WORKER_DIR/cron" "$BIN_DIR"
copy_scripts
cat > "$WORKER_DIR/cron/jobs.json" <<'EOF'
{"jobs": [{"id": "1", "name": "default_job", "schedule": "0 */4 * * *"}]}
EOF
cat > "$WORKER_DIR/cron/jobs.custom.json" <<'EOF'
{"jobs": [{"id": "2", "name": "custom_job", "schedule": "0 */2 * * *"}]}
EOF
rm -f "$WORKER_DIR/cron/jobs.json"
assert_exit "$BIN_DIR/merge-jobs.sh" 0 "merge-jobs.sh succeeds with valid inputs"

# --- 2. Merged jobs.json structure ---
assert_contains "$WORKER_DIR/cron/jobs.json" '"jobs"' "merged jobs.json has jobs key"

# --- 3. Custom jobs override base by id ---
mkdir -p "$COMMON_DIR" "$WORKER_DIR/cron" "$BIN_DIR"
cat > "$WORKER_DIR/cron/jobs.json" <<'EOF'
{"jobs": [{"id": "1", "name": "base_job", "schedule": "0 */4 * * *", "enabled": true}]}
EOF
cat > "$WORKER_DIR/cron/jobs.custom.json" <<'EOF'
{"jobs": [{"id": "1", "name": "custom_job", "schedule": "0 */2 * * *"}]}
EOF
assert_exit "$BIN_DIR/merge-jobs.sh" 0 "merge-jobs.sh handles id conflict override"
assert_contains "$WORKER_DIR/cron/jobs.json" '"custom_job"' "merged jobs.json contains custom job name"

# --- 4. Missing base jobs.json creates it ---
mkdir -p "$COMMON_DIR" "$WORKER_DIR/cron" "$BIN_DIR"
rm -f "$WORKER_DIR/cron/jobs.json" "$WORKER_DIR/cron/jobs.custom.json"
cat > "$WORKER_DIR/cron/jobs.custom.json" <<'EOF'
{"jobs": [{"id": "1", "name": "only_custom", "schedule": "0 * * * *"}]}
EOF
assert_exit "$BIN_DIR/merge-jobs.sh" 0 "merge-jobs.sh handles missing base jobs.json"

# --- 5. Missing custom exits 1 ---
mkdir -p "$COMMON_DIR" "$WORKER_DIR/cron" "$BIN_DIR"
cat > "$WORKER_DIR/cron/jobs.json" <<'EOF'
{"jobs": [{"id": "1", "name": "base", "schedule": "0 * * * *"}]}
EOF
rm -f "$WORKER_DIR/cron/jobs.custom.json"
assert_exit "$BIN_DIR/merge-jobs.sh" 1 "merge-jobs.sh exits 1 when custom is missing"

# --- 6. Corrupt custom JSON ---
mkdir -p "$COMMON_DIR" "$WORKER_DIR/cron" "$BIN_DIR"
cat > "$WORKER_DIR/cron/jobs.json" <<'EOF'
{"jobs": []}
EOF
cat > "$WORKER_DIR/cron/jobs.custom.json" <<'EOF'
{invalid json}
EOF
assert_exit "$BIN_DIR/merge-jobs.sh" 1 "merge-jobs.sh exits 1 when custom JSON is corrupt"

# --- 7. No profiles with custom exits 1 ---
mkdir -p "$COMMON_DIR" "$BIN_DIR"
cat > "$COMMON_DIR/jobs.json" <<'EOF'
{"jobs": []}
EOF
assert_exit "$BIN_DIR/merge-jobs.sh" 1 "merge-jobs.sh exits 1 when no profiles with custom"

echo ""

# === merge-soul.sh ===
echo "=== merge-soul.sh ==="

# --- 1. Happy path ---
mkdir -p "$COMMON_DIR" "$WORKER_DIR" "$BIN_DIR"
copy_scripts
cat > "$COMMON_DIR/SOUL.md" <<'EOF'
# Common SOUL
System instructions for all profiles
EOF
cat > "$WORKER_DIR/SOUL.custom.md" <<'EOF'
# Worker SOUL
Worker-specific personality
EOF
rm -f "$WORKER_DIR/SOUL.md"
assert_exit "$BIN_DIR/merge-soul.sh" 0 "merge-soul.sh succeeds with valid inputs"

# --- 2. Merged SOUL contains both custom and common ---
assert_contains "$WORKER_DIR/SOUL.md" "Worker-specific personality" "merged SOUL contains custom content"
assert_contains "$WORKER_DIR/SOUL.md" "System instructions" "merged SOUL contains common content"

# --- 3. Custom SOUL comes before common ---
assert_contains "$WORKER_DIR/SOUL.md" "Worker SOUL" "merged SOUL starts with custom section"

# --- 4. Missing custom exits 1 ---
mkdir -p "$COMMON_DIR" "$WORKER_DIR" "$BIN_DIR"
cat > "$COMMON_DIR/SOUL.md" <<'EOF'
# Common SOUL
System instructions
EOF
rm -f "$WORKER_DIR/SOUL.custom.md" "$WORKER_DIR/SOUL.md"
assert_exit "$BIN_DIR/merge-soul.sh" 1 "merge-soul.sh exits 1 when custom SOUL is missing"

# --- 5. Missing common exits 1 ---
mkdir -p "$COMMON_DIR" "$WORKER_DIR" "$BIN_DIR"
cat > "$WORKER_DIR/SOUL.custom.md" <<'EOF'
# Worker SOUL
Worker personality
EOF
rm -f "$COMMON_DIR/SOUL.md" "$WORKER_DIR/SOUL.md"
assert_exit "$BIN_DIR/merge-soul.sh" 1 "merge-soul.sh exits 1 when common SOUL is missing"

# --- 6. Empty custom SOUL ---
mkdir -p "$COMMON_DIR" "$WORKER_DIR" "$BIN_DIR"
cat > "$COMMON_DIR/SOUL.md" <<'EOF'
# Common SOUL
System instructions
EOF
cat > "$WORKER_DIR/SOUL.custom.md" <<'EOF'
EOF
rm -f "$WORKER_DIR/SOUL.md"
assert_exit "$BIN_DIR/merge-soul.sh" 0 "merge-soul.sh handles empty custom SOUL"

# --- 7. No profiles with custom exits 1 ---
mkdir -p "$COMMON_DIR" "$BIN_DIR"
cat > "$COMMON_DIR/SOUL.md" <<'EOF'
# Common SOUL
System instructions
EOF
assert_exit "$BIN_DIR/merge-soul.sh" 1 "merge-soul.sh exits 1 when no profiles with custom"

# --- 8. Multiple profiles merge ---
mkdir -p "$COMMON_DIR" "$WORKER_DIR" "$PROFILES_DIR/reviewer" "$PROFILES_DIR/researcher" "$BIN_DIR"
cat > "$COMMON_DIR/SOUL.md" <<'EOF'
# Common SOUL
System instructions for all profiles
EOF
cat > "$WORKER_DIR/SOUL.custom.md" <<'EOF'
# Worker SOUL
Worker personality
EOF
cat > "$PROFILES_DIR/reviewer/SOUL.custom.md" <<'EOF'
# Reviewer SOUL
Reviewer personality
EOF
cat > "$PROFILES_DIR/researcher/SOUL.custom.md" <<'EOF'
# Research SOUL
Researcher personality
EOF
rm -f "$WORKER_DIR/SOUL.md" "$PROFILES_DIR/reviewer/SOUL.md" "$PROFILES_DIR/researcher/SOUL.md"
assert_exit "$BIN_DIR/merge-soul.sh" 0 "merge-soul.sh merges multiple profiles at once"
assert_file_exists "$WORKER_DIR/SOUL.md" "worker has merged SOUL"
assert_file_exists "$PROFILES_DIR/reviewer/SOUL.md" "reviewer has merged SOUL"
assert_file_exists "$PROFILES_DIR/researcher/SOUL.md" "researcher has merged SOUL"

# --- 9. Atomic writes via mktemp ---
mkdir -p "$COMMON_DIR" "$WORKER_DIR" "$BIN_DIR"
cat > "$COMMON_DIR/SOUL.md" <<'EOF'
# Common SOUL
System instructions
EOF
cat > "$WORKER_DIR/SOUL.custom.md" <<'EOF'
# Worker SOUL
Worker personality
EOF
rm -f "$WORKER_DIR/SOUL.md"
assert_exit "$BIN_DIR/merge-soul.sh" 0 "merge-soul.sh uses atomic writes"

echo ""

# === link-scripts.sh ===
echo "=== link-scripts.sh ==="

# --- 1. link-skills.sh happy path ---
mkdir -p "$PROFILES_DIR/common" "$WORKER_DIR" "$PROFILES_DIR/common/skills" "$BIN_DIR"
copy_scripts
touch "$PROFILES_DIR/common/skills/test-skill.md"
cat > "$WORKER_DIR/skills" <<'EOF'
test-skill
EOF
rm -f "$WORKER_DIR/skills/test-skill.md" "$WORKER_DIR/skills"
assert_exit "$BIN_DIR/link-skills.sh" 0 "link-skills.sh handles linking skills"

# --- 2. link-plugins.sh happy path ---
mkdir -p "$PROFILES_DIR/common" "$WORKER_DIR" "$PROFILES_DIR/common/link-tools" "$BIN_DIR"
touch "$PROFILES_DIR/common/link-tools/test-plugin"
cat > "$WORKER_DIR/link-tools" <<'EOF'
test-plugin
EOF
rm -f "$WORKER_DIR/link-tools/test-plugin" "$WORKER_DIR/link-tools"
assert_exit "$BIN_DIR/link-plugins.sh" 0 "link-plugins.sh handles linking plugins"

echo ""

# === Final summary ===
echo ""
echo "=========================================="
echo "TOTAL: $TOTAL tests"
echo "PASS:  $PASS"
echo "FAIL:  $FAIL"
echo "=========================================="
exit "$FAIL"
