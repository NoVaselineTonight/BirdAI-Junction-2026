#!/usr/bin/env bash
# Main: measure every model trained today on the same held-out frames and the same (newest) labels.
# Waits for the 26-day evaluation to finish first. Output: data/logs/history-<round>-<size>.log
export PATH=$HOME/.local/bin:$PATH
cd ~/birdai || exit 1
L=data/logs/history.log
echo "history waiting $(date +%H:%M:%S)" > $L
until grep -q "curves done" data/logs/v4eval.log 2>/dev/null; do sleep 10; done
for pair in quick:640 v2a:960 v2a:640 v3:640; do
  r=${pair%%:*}; s=${pair##*:}
  [ -e models_$r/student/$s/feeder.onnx ] || { echo "missing models_$r/student/$s" >> $L; continue; }
  uv run --group train python data/curve.py data/dataset_v4 models_$r $s 2>&1 | grep -v "Warning\|warn\|INFO" > data/logs/history-$r-$s.log
  echo "$r $s exit ${PIPESTATUS[0]} $(date +%H:%M:%S)" >> $L
done
echo "history done $(date +%H:%M:%S)" >> $L
