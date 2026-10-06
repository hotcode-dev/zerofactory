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
#   - Python (primary language): ruff is MANDATORY for the format/lint
#     phase — when missing, a pinned version (see RUFF_VERSION) is
#     auto-installed via `uv tool install` or `pip install --user`, and
#     the gate exits non-zero with the captured install error if that
#     fails (e.g. PEP 668 externally-managed environments);
#     `python3 -m compileall` for the build/typecheck phase (stdlib only);
#     `python3 -m pytest tests/` for tests (pytest is the framework defined
#     by tests/conftest.py) — when missing, the pinned test stack (pytest +
#     plugin runtime deps, see TEST_* versions below) is auto-installed.
#     The suite is pytest-based and never falls back to unittest discovery.
#   - Node.js: package.json defines only `build:css` (dashboard stylesheet
#     regeneration, an optional tooling task) — nothing is wired here.

set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# Pinned ruff version for deterministic lint/format behavior.
# Bump deliberately after verification — never use @latest.
RUFF_VERSION="0.16.9"

# Pinned test stack for deterministic test behavior (pytest is the framework
# defined by tests/conftest.py; the remaining modules are the plugin runtime
# deps imported by the suite). Bump deliberately after verification.
PYTEST_VERSION="9.0.3"
FASTAPI_VERSION="0.133.1"
HTTPX_VERSION="0.28.1"
PYDANTIC_VERSION="2.13.4"
PYYAML_VERSION="6.0.3"

run_format() {
  echo "▶ Zero Factory precommit: format & lint"
  install_log=""
  if ! command -v ruff >/dev/null 2>&1; then
    echo "  (info) ruff not found on PATH — attempting to install ruff==${RUFF_VERSION}..."
    if command -v uv >/dev/null 2>&1; then
      install_log="$(uv tool install "ruff==${RUFF_VERSION}" 2>&1)" || true
    elif command -v pip3 >/dev/null 2>&1; then
      install_log="$(pip3 install --user "ruff==${RUFF_VERSION}" 2>&1)" || true
    elif command -v pip >/dev/null 2>&1; then
      install_log="$(pip install --user "ruff==${RUFF_VERSION}" 2>&1)" || true
    fi
  fi
  if command -v ruff >/dev/null 2>&1; then
    ruff check --fix .
    ruff format .
  else
    echo "  (error) ruff is required for Zero Factory precommit verification but could not be installed."
    if [ -n "$install_log" ]; then
      echo "  Install failure output (why ruff is missing):"
      printf '%s\n' "$install_log" | sed 's/^/    /'
    fi
    echo "  (hint) On PEP 668 (externally-managed) systems, pip install --user is blocked by the"
    echo "         OS Python distribution. Install the pinned ruff instead, e.g.:"
    echo "           uv tool install ruff==${RUFF_VERSION}"
    exit 1
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
  # hermetic env defaults) and the suite imports the plugin runtime deps.
  # It CANNOT run under plain unittest discovery (module-level `import pytest`
  # plus conftest fixtures cause misleading collection errors), so missing
  # test tooling is self-bootstrapped (pinned) exactly like ruff above.
  test_deps=(
    "pytest==${PYTEST_VERSION}"
    "fastapi==${FASTAPI_VERSION}"
    "httpx==${HTTPX_VERSION}"
    "pydantic==${PYDANTIC_VERSION}"
    "PyYAML==${PYYAML_VERSION}"
  )
  install_log=""
  if ! python3 -c "import pytest, fastapi, httpx, yaml" >/dev/null 2>&1; then
    echo "  (info) pinned test stack not importable — attempting to install..."
    if command -v uv >/dev/null 2>&1; then
      # venv interpreters install directly; bare system/tool interpreters
      # need --system.
      install_log="$(uv pip install --python "$(command -v python3)" "${test_deps[@]}" 2>&1)" \
        || install_log="$(uv pip install --system --python "$(command -v python3)" "${test_deps[@]}" 2>&1)" \
        || true
    elif python3 -m pip --version >/dev/null 2>&1; then
      install_log="$(python3 -m pip install --user "${test_deps[@]}" 2>&1)" || true
    elif command -v pip3 >/dev/null 2>&1; then
      install_log="$(pip3 install --user "${test_deps[@]}" 2>&1)" || true
    fi
  fi
  if python3 -c "import pytest, fastapi, httpx, yaml" >/dev/null 2>&1; then
    python3 -m pytest tests/ -q
  else
    echo "  (error) pytest + plugin runtime deps (fastapi, httpx, pydantic, PyYAML) are"
    echo "         required for Zero Factory precommit verification but could not be installed."
    if [ -n "$install_log" ]; then
      echo "  Install failure output (why the test stack is missing):"
      printf '%s\n' "$install_log" | sed 's/^/    /'
    fi
    echo "  (hint) Install the pinned test stack into the interpreter running this gate, e.g.:"
    echo "           uv pip install --system --python \"\$(command -v python3)\" ${test_deps[*]}"
    exit 1
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
