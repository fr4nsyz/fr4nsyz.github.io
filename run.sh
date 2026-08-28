#!/usr/bin/env bash
# Build the site and serve it, printing the addresses to go to.
set -euo pipefail

cd "$(dirname "$0")"

PORT="${1:-${PORT:-8000}}"

LAN_IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || true)"

echo "building..."
python3 build.py

echo
echo "serving _site/ on :$PORT"
if [ -n "$LAN_IP" ]; then
  echo "  local:  http://localhost:$PORT"
  echo "  lan:    http://$LAN_IP:$PORT"
else
  echo "  url:    http://localhost:$PORT"
fi
echo "press ctrl-c to stop"
echo

exec python3 -m http.server -d _site "$PORT"