#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMMON_SKILLS_DIR="$ROOT_DIR/profiles/common/skills"

if [[ ! -d "$COMMON_SKILLS_DIR" ]]; then
  echo "Error: common skills directory not found: $COMMON_SKILLS_DIR" >&2
  exit 1
fi

shopt -s nullglob
for profile_dir in "$ROOT_DIR"/profiles/*; do
  [[ -d "$profile_dir" ]] || continue

  profile_name="$(basename "$profile_dir")"
  [[ "$profile_name" == "common" ]] && continue
  # Ignore dot directories (like .gitignore file, etc. though nullglob helps, let's just make sure)
  [[ "$profile_name" == .* ]] && continue

  PROFILE_SKILLS_DIR="$profile_dir/skills"
  mkdir -p "$PROFILE_SKILLS_DIR"
  
  for skill_dir in "$COMMON_SKILLS_DIR"/*; do
    [[ -d "$skill_dir" ]] || continue
    skill_name="$(basename "$skill_dir")"
    
    ln -sfn "../../common/skills/$skill_name" "$PROFILE_SKILLS_DIR/$skill_name"
    echo "Linked $skill_name to $profile_name profile"
  done
done
