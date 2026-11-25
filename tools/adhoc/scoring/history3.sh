#!/usr/bin/env bash
# Main: every model trained today, scored on the same held-out frames against the newest labels (dataset_v5),
# at the lowest priority. Waits for the dataset build to finish first. Output: data/logs/history3.log (ROW lines).
export PATH=$HOME/.local/bin:$PATH
cd ~/birdai || exit 1
L=data/logs/history3.log
: > $L
until grep -q "dataset exit 0" data/logs/v5build.log 2>/dev/null; do sleep 10; done
for pair in quick:640 v2a:640 v2a:960 v3:640 v3:960 v4:640 v4:960; do
  r=${pair%%:*}; s=${pair##*:}
  nice -n 19 uv run --group train python data/curve2.py data/dataset_v5 models_$r/student/$s "$r-$s" 2>&1 | grep "^ROW\|Error\|error" >> $L
done
echo "history3 done $(date +%H:%M:%S)" >> $L
