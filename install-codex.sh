#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# GEO Codex Installer
# Installs Python package + checks official Codex login flow
# ============================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_info() { echo -e "${BLUE}→ $1${NC}"; }
print_ok() { echo -e "${GREEN}✓ $1${NC}"; }
print_warn() { echo -e "${YELLOW}⚠ $1${NC}"; }
print_err() { echo -e "${RED}✗ $1${NC}"; }

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_CMD=""

if command -v python3 >/dev/null 2>&1; then
  PYTHON_CMD="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_CMD="python"
else
  print_err "Python 3.8+ is required"
  exit 1
fi

print_info "Using Python: $($PYTHON_CMD --version)"

print_info "Installing package in editable mode..."
set +e
"$PYTHON_CMD" -m pip install -e "$ROOT_DIR"
rc=$?
set -e
if [ "$rc" -ne 0 ]; then
  print_warn "Editable install failed, retrying user install..."
  set +e
  "$PYTHON_CMD" -m pip install --user "$ROOT_DIR"
  rc=$?
  set -e
  if [ "$rc" -ne 0 ]; then
    print_warn "pip install did not complete. You can still run:"
    echo "  PYTHONPATH=\"$ROOT_DIR/src\" python3 -m geo.cli doctor"
  else
    print_ok "Installed geo CLI (user mode)"
  fi
else
  print_ok "Installed geo CLI (editable mode)"
fi

print_info "Checking Codex CLI..."
if ! command -v codex >/dev/null 2>&1; then
  print_warn "codex CLI not found in PATH."
  echo "  Install Codex app/CLI first, then run: codex login"
  echo "  You can still run local analysis commands now."
else
  print_ok "codex CLI found: $(codex --version 2>/dev/null || true)"
  set +e
  geo doctor
  rc=$?
  set -e
  if [ "$rc" -ne 0 ]; then
    print_warn "Codex login likely missing. Run: codex login"
  fi
fi

echo ""
print_ok "Codex setup finished."
echo "Try:"
echo "  geo doctor"
echo "  geo quick https://example.com"
echo "  geo audit https://example.com"
