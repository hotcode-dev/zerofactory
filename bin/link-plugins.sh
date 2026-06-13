#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMMON_PLUGINS_DIR="$ROOT_DIR/profiles/common/plugins"

if [[ ! -d "$COMMON_PLUGINS_DIR" ]]; then
  echo "Error: common plugins directory not found: $COMMON_PLUGINS_DIR" >&2
  exit 1
fi

shopt -s nullglob
for profile_dir in "$ROOT_DIR"/profiles/*; do
  [[ -d "$profile_dir" ]] || continue

  profile_name="$(basename "$profile_dir")"
  [[ "$profile_name" == "common" ]] && continue
  # Ignore dot directories (like .gitignore file, etc. though nullglob helps, let's just make sure)
  [[ "$profile_name" == .* ]] && continue

  PROFILE_PLUGINS_DIR="$profile_dir/plugins"
  mkdir -p "$PROFILE_PLUGINS_DIR"
  
  for plugin_dir in "$COMMON_PLUGINS_DIR"/*; do
    [[ -d "$plugin_dir" ]] || continue
    plugin_name="$(basename "$plugin_dir")"
    
    ln -sfn "../../common/plugins/$plugin_name" "$PROFILE_PLUGINS_DIR/$plugin_name"
    echo "Linked $plugin_name to $profile_name profile"
  done
done
