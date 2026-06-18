#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMMON_CONFIG="$ROOT_DIR/profiles/common/config.yaml"
CUSTOM_CONFIGS_DIR="$ROOT_DIR/profiles"
BASE_SCHEMA="$ROOT_DIR/profiles/config.schema.json"
OVERRIDE_SCHEMA="$ROOT_DIR/profiles/config.override.schema.json"
SCHEMA_CHECK="$ROOT_DIR/bin/check-schema.py"

if ! command -v yq >/dev/null 2>&1; then
  echo "Error: yq is required but not found in PATH." >&2
  echo "Install yq v4: https://github.com/mikefarah/yq" >&2
  exit 1
fi

# ---------- schema validation -------------------------------------------
validate_config() {
  local file="$1"
  local schema="$2"
  local label="$3"

  if [[ ! -f "$file" ]]; then
    echo "WARN: $label not found — skipping validation: $file" >&2
    return 0
  fi

  python3 "$SCHEMA_CHECK" "$file" "$schema"
  if [[ $? -eq 0 ]]; then
    echo "  OK: $label passes schema validation"
  else
    echo "  FAIL: $label fails schema validation" >&2
    return 1
  fi
}

echo "=== Config schema validation ==="

# Validate common base against base schema
validate_config "$COMMON_CONFIG" "$BASE_SCHEMA" "profiles/common/config.yaml"

# Validate every profile's custom override against override schema
profile_errors=0
for profile_dir in "$CUSTOM_CONFIGS_DIR"/*/; do
  [[ -d "$profile_dir" ]] || continue
  profile_name="$(basename "$profile_dir")"
  [[ "$profile_name" == "common" ]] && continue

  custom_cfg="$profile_dir/config.custom.yaml"
  if [[ -f "$custom_cfg" ]]; then
    validate_config "$custom_cfg" "$OVERRIDE_SCHEMA" "profiles/$profile_name/config.custom.yaml" || ((profile_errors++))
  fi
done

if [[ $profile_errors -gt 0 ]]; then
  echo "ERROR: $profile_errors custom config(s) failed schema validation." >&2
  exit 1
fi

echo "=== Validation passed ==="

# ---------- merge logic -------------------------------------------------
merge_one() {
  local profile_name="$1"
  local output_file="$ROOT_DIR/profiles/$profile_name/config.yaml"
  local profile_custom_config="$ROOT_DIR/profiles/$profile_name/config.custom.yaml"

  if [[ ! -f "$profile_custom_config" ]]; then
    echo "Error: profile custom config not found: $profile_custom_config" >&2
    return 1
  fi

  mkdir -p "$(dirname "$output_file")"

  # Merge order: common base first, profile custom overrides second.
  yq eval-all '. as $item ireduce ({}; . * $item )' \
    "$COMMON_CONFIG" \
    "$profile_custom_config" > "$output_file"

  echo "Merged config written to: $output_file"
}

shopt -s nullglob
found_any=false
for profile_dir in "$ROOT_DIR"/profiles/*/; do
  [[ -d "$profile_dir" ]] || continue

  profile_name="$(basename "$profile_dir")"
  [[ "$profile_name" == "common" ]] && continue

  found_any=true
  merge_one "$profile_name"
done

if [[ "$found_any" == false ]]; then
  echo "Error: no profiles found under $ROOT_DIR/profiles" >&2
  exit 1
fi

echo ""
echo "Config merge complete."
