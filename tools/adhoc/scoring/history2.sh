#!/usr/bin/env bash
# Main: every model trained today, scored on the same held-out frames against the newest labels.
export PATH=$HOME/.local/bin:$PATH
cd ~/birdai || exit 1
D=${1:-data/dataset_v4}
L=data/logs/history2.log
: > $L
for pair in quick:640 v1:960 v2a:640 v2a:960 v3:640 v3:960 v4:640 v4:960; do
  r=${pair%%:*}; s=${pair##*:}
  uv run --group train python data/curve2.py $D models_$r/student/$s "$r-$s" 2>&1 | grep "^ROW\|Error\|error" >> $L
done
echo "history2 done $(date +%H:%M:%S)" >> $L
