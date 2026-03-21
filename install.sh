#!/usr/bin/env bash
set -euo pipefail

# Backward-compatible entrypoint.
# Default now recommends Codex flow; Claude flow remains supported.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ "${1:-}" = "--claude" ]; then
  exec "$ROOT_DIR/install-claude.sh"
fi

if [ "${1:-}" = "--codex" ] || [ -z "${1:-}" ]; then
  exec "$ROOT_DIR/install-codex.sh"
fi

echo "Usage: ./install.sh [--codex|--claude]"
exit 1
