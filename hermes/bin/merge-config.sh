#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMMON_CONFIG="$ROOT_DIR/profiles/common/config.yaml"

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "Usage: $0 <profile-name|all> [output-file]" >&2
  echo "Example: $0 builder $ROOT_DIR/profiles/builder/config.yaml" >&2
  echo "Example: $0 all" >&2
  exit 1
fi

PROFILE_NAME="$1"
if [[ "$PROFILE_NAME" == "common" ]]; then
  echo "Error: profile-name must not be 'common'." >&2
  exit 1
fi

if ! command -v yq >/dev/null 2>&1; then
  echo "Error: yq is required but not found in PATH." >&2
  echo "Install yq v4: https://github.com/mikefarah/yq" >&2
  exit 1
fi

if [[ ! -f "$COMMON_CONFIG" ]]; then
  echo "Error: common config not found: $COMMON_CONFIG" >&2
  exit 1
fi

merge_one() {
  local profile_name="$1"
  local output_file="$2"
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

if [[ "$PROFILE_NAME" == "all" ]]; then
  if [[ $# -eq 2 ]]; then
    echo "Error: output-file is not supported when using 'all'." >&2
    exit 1
  fi

  shopt -s nullglob
  found_any=false
  for profile_dir in "$ROOT_DIR"/profiles/*; do
    [[ -d "$profile_dir" ]] || continue

    profile_name="$(basename "$profile_dir")"
    [[ "$profile_name" == "common" ]] && continue

    found_any=true
    merge_one "$profile_name" "$profile_dir/config.yaml"
  done

  if [[ "$found_any" == false ]]; then
    echo "Error: no profiles found under $ROOT_DIR/profiles" >&2
    exit 1
  fi

  exit 0
fi

OUTPUT_FILE="${2:-$ROOT_DIR/profiles/$PROFILE_NAME/config.yaml}"
merge_one "$PROFILE_NAME" "$OUTPUT_FILE"
