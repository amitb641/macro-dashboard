#!/usr/bin/env bash
# Local preview server for the macro dashboard.
# Usage:
#   scripts/dev-preview.sh              # serves on :8765
#   scripts/dev-preview.sh 8080         # custom port
#   scripts/dev-preview.sh 8765 banks   # open a specific tab on launch
set -euo pipefail

PORT="${1:-8765}"
TAB="${2:-}"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

URL="http://localhost:${PORT}/"
[ -n "$TAB" ] && URL="${URL}#tab=${TAB}"

echo "Serving $ROOT at $URL"
echo "Ctrl-C to stop."

# Prefer Python 3
exec python3 -m http.server "$PORT"
