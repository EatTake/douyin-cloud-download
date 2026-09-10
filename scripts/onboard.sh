#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON=""
for candidate in python3.12 python3; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)' 2>/dev/null; then
    PYTHON="$candidate"
    break
  fi
done
if [ -z "$PYTHON" ]; then
  echo "Python 3.12 is required." >&2
  exit 2
fi
GLOBAL_ARGS=()
ONBOARD_ARGS=()
while [ "$#" -gt 0 ]; do
  case "$1" in
    --codex-home)
      GLOBAL_ARGS+=("$1" "$2")
      shift 2
      ;;
    --drive|--quick-start|--dry-run)
      if [ "$1" = "--drive" ]; then
        ONBOARD_ARGS+=("$1" "$2")
        shift 2
      else
        ONBOARD_ARGS+=("$1")
        shift
      fi
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 2
      ;;
  esac
done
exec "$PYTHON" "$SCRIPT_DIR/setup.py" "${GLOBAL_ARGS[@]}" onboard "${ONBOARD_ARGS[@]}"
