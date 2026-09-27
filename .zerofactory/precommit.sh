#!/usr/bin/env bash
# Zero Factory precommit script — hotcode-dev/zerofactory
#
# Deterministically verifies format → build → test before the dispatcher
# commits a worktree branch and opens a PR.
#
# Usage:
#   .zerofactory/precommit.sh [all|format|build|test|install-hook]
#
# Tooling precedence:
#   - Python (primary language): ruff when available, else no-op notice;
#     `python3 -m compileall` for the build/typecheck phase (stdlib only);
#     `python3 -m pytest tests/` for tests (pytest is the framework defined
#     by tests/conftest.py).
#   - Node.js: package.json defines only `build:css` (dashboard stylesheet
#     regeneration, an optional tooling task) — nothing is wired here.

set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

run_format() {
  echo "▶ Zero Factory precommit: format"
  if command -v ruff >/dev/null 2>&1; then
    ruff format .
    ruff check --fix .
  else
    echo "  (info) ruff not available — skipping Python format (no formatter configured in package.json)"
  fi
}

run_build() {
  echo "▶ Zero Factory precommit: build"
  # Static compilation/typecheck of all Python sources (stdlib only).
  python3 -m compileall -q .
  echo "  Python sources compile cleanly."
  # No build system (Makefile/Cargo/go.mod) defined for this repository;
  # package.json build:css is an optional dashboard stylesheet regeneration.
  echo "  (info) no further build step defined for this repository."
}

run_test() {
  echo "▶ Zero Factory precommit: test"
  # pytest is the test framework defined by tests/conftest.py (fixtures +
  # hermetic env defaults). Fallback to unittest discovery if pytest is missing.
  if python3 -m pytest --version >/dev/null 2>&1; then
    python3 -m pytest tests/ -q
  else
    echo "  (info) pytest not available — falling back to unittest discovery."
    python3 -m unittest discover -s tests -v
  fi
}

install_hook() {
  HOOK_DIR="$(git rev-parse --git-path hooks 2>/dev/null || echo ".git/hooks")"
  mkdir -p "$HOOK_DIR"
  ln -sf "../../.zerofactory/precommit.sh" "$HOOK_DIR/pre-commit"
  chmod +x "$HOOK_DIR/pre-commit"
  echo "✓ Linked .zerofactory/precommit.sh -> $HOOK_DIR/pre-commit"
}

case "${1:-all}" in
  format)       run_format ;;
  build)        run_build ;;
  test)         run_test ;;
  install-hook) install_hook ;;
  all|*)
    run_format
    run_build
    run_test
    ;;
esac

echo "✓ Zero Factory precommit checks passed!"
