#!/usr/bin/env bash
# Stop the waiting (not yet training) last-round launcher so it can be re-armed with other epoch counts.
grep -q "dataset here" ~/birdai/data/logs/v5train.log && { echo "already training, not stopping"; exit 1; }
for p in $(pgrep -f "data/train-v5[.]sh"); do kill "$p" 2>/dev/null && echo "killed $p"; done
