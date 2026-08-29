#!/usr/bin/env bash
# Replay a captured run at watchable speed.
#
#   scripts/replay.sh [log]
#
# A real run spends most of its wall clock cloning the repository, installing
# dependencies, and downloading a browser. Replaying keeps the output verbatim
# and removes only the waiting, so a recording stays honest without being
# twenty minutes long.
#
# Regenerate the capture with:
#   python -u -m src.main --repo <url> --ref <sha> --issue issue.txt \
#     --max-attempts 2 2>&1 | tee demo-live.log

set -euo pipefail

log="${1:-demo-live.log}"

while IFS= read -r line; do
  printf '%s\n' "$line"
  case "$line" in
    # Pause where the real run pauses, so the shape of the loop stays visible.
    *"generating reproduction test"*) sleep 1.5 ;;
    *"running in sandbox"*)           sleep 2.0 ;;
    *"BUG REPRODUCED"*)               sleep 1.0 ;;
    *)                                sleep 0.3 ;;
  esac
done < "$log"
