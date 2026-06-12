#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ $# -ne 0 ]]; then
  echo "Usage: $0" >&2
  exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "Error: jq is required but not found in PATH." >&2
  exit 1
fi

merge_one() {
  local profile_name="$1"
  local output_file="$ROOT_DIR/profiles/$profile_name/cron/jobs.json"
  local base_jobs_file="$ROOT_DIR/profiles/$profile_name/cron/jobs.json"
  local custom_jobs_file="$ROOT_DIR/profiles/$profile_name/cron/jobs.custom.json"
  local tmp_output

  if [[ ! -f "$base_jobs_file" ]]; then
    mkdir -p "$(dirname "$base_jobs_file")"
    echo '{"jobs": []}' > "$base_jobs_file"
  fi

  if [[ ! -f "$custom_jobs_file" ]]; then
    echo "Error: jobs custom file not found: $custom_jobs_file" >&2
    return 1
  fi

  if ! jq -e . "$custom_jobs_file" >/dev/null 2>&1; then
    echo "Error: jobs custom file is not valid JSON: $custom_jobs_file" >&2
    return 1
  fi

  mkdir -p "$(dirname "$output_file")"
  tmp_output="$(mktemp "${TMPDIR:-.}/merge-jobs.XXXXXX")"

  if jq -e . "$base_jobs_file" >/dev/null 2>&1; then
    # Custom overrides base; jobs with matching id are merged object-wise.
    jq -n \
      --argfile base "$base_jobs_file" \
      --argfile custom "$custom_jobs_file" \
      '
        def to_doc:
          if type == "object" then .
          elif type == "array" then {jobs: .}
          else {}
          end;

        def merge_jobs($baseJobs; $customJobs):
          ($baseJobs // []) as $b
          | ($customJobs // []) as $c
          | ($c | map(select(.id? != null)) | map({key: .id, value: .}) | from_entries) as $customById
          | ($b | map(.id? // empty)) as $baseIds
          | ($b | map(if .id? != null and ($customById[.id] | type) != "null" then . * $customById[.id] else . end))
            + ($c | map(select(.id? != null)) | map(. as $job | select(($baseIds | index($job.id)) | not)));

        ($base | to_doc) as $b
        | ($custom | to_doc) as $c
        | ($b * $c)
        | .jobs = merge_jobs($b.jobs; $c.jobs)
      ' > "$tmp_output"
  else
    # Recover from an empty/corrupt base file by using custom as the source of truth.
    jq -n --argfile custom "$custom_jobs_file" 'if ($custom | type) == "array" then {jobs: $custom} else $custom end' > "$tmp_output"
  fi

  mv "$tmp_output" "$output_file"

  echo "Merged jobs written to: $output_file"
}

shopt -s nullglob
found_any=false
for profile_dir in "$ROOT_DIR"/profiles/*; do
  [[ -d "$profile_dir" ]] || continue

  profile_name="$(basename "$profile_dir")"
  [[ "$profile_name" == "common" ]] && continue

  if [[ -f "$profile_dir/cron/jobs.custom.json" ]]; then
    found_any=true
    merge_one "$profile_name"
  fi
done

if [[ "$found_any" == false ]]; then
  echo "Error: no profiles with cron/jobs.custom.json found under $ROOT_DIR/profiles" >&2
  exit 1
fi
