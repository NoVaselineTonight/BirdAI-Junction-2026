#!/usr/bin/env bash
# Stop a waiting worker chain (the one that waits for the videos); downloads are left alone.
for p in $(pgrep -f "data/worker[8][.]sh"); do kill "$p" 2>/dev/null && echo "killed $p"; done
