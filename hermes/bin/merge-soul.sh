#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMMON_SOUL="$ROOT_DIR/profiles/common/SOUL.md"

if [[ $# -ne 0 ]]; then
  echo "Usage: $0" >&2
  exit 1
fi

if [[ ! -f "$COMMON_SOUL" ]]; then
  echo "Error: common SOUL file not found: $COMMON_SOUL" >&2
  exit 1
fi

merge_one() {
  local profile_name="$1"
  local output_file="$ROOT_DIR/profiles/$profile_name/SOUL.md"
  local profile_custom_soul="$ROOT_DIR/profiles/$profile_name/SOUL.custom.md"
  local tmp_output

  if [[ ! -f "$profile_custom_soul" ]]; then
    echo "Error: profile custom SOUL not found: $profile_custom_soul" >&2
    return 1
  fi

  mkdir -p "$(dirname "$output_file")"
  tmp_output="$(mktemp "${TMPDIR:-.}/merge-soul.XXXXXX")"

  # Profile custom SOUL comes first; common SOUL is appended last.
  {
    cat "$profile_custom_soul"
    echo
    cat "$COMMON_SOUL"
  } > "$tmp_output"

  mv "$tmp_output" "$output_file"
  echo "Merged SOUL written to: $output_file"
}

shopt -s nullglob
found_any=false
for profile_dir in "$ROOT_DIR"/profiles/*; do
  [[ -d "$profile_dir" ]] || continue

  profile_name="$(basename "$profile_dir")"
  [[ "$profile_name" == "common" ]] && continue

  if [[ -f "$profile_dir/SOUL.custom.md" ]]; then
    found_any=true
    merge_one "$profile_name"
  fi
done

if [[ "$found_any" == false ]]; then
  echo "Error: no profiles with SOUL.custom.md found under $ROOT_DIR/profiles" >&2
  exit 1
fi
