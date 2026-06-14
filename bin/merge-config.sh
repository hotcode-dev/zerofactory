#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMMON_CONFIG="$ROOT_DIR/profiles/common/config.yaml"

if [[ $# -ne 0 ]]; then
  echo "Usage: $0" >&2
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

  local soul_file="$ROOT_DIR/profiles/$profile_name/SOUL.md"
  if [[ -f "$soul_file" ]]; then
    SOUL_CONTENT="$(cat "$soul_file")" yq eval '.system_prompt = env(SOUL_CONTENT)' -i "$output_file"
  fi

  echo "Merged config written to: $output_file"
}

shopt -s nullglob
found_any=false
for profile_dir in "$ROOT_DIR"/profiles/*; do
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
