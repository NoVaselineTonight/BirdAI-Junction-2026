#!/bin/bash
cd ~/birdai
L=data/logs/rescore.log; : > $L
for spec in "models_v4/student v4-640" "models_v4/student/960 v4-960" "models_v5/student/640 v5-640" "models_v5/student/960 v5-960"; do
  set -- $spec
  ( PYTHONPATH=. .venv/bin/python data/rescore.py data/dataset_v5 $1 $2 2>&1 | grep -v "Warning\|warn\|INFO" > data/logs/rescore-$2.log ) &
done
wait
cat data/logs/rescore-v4-640.log data/logs/rescore-v4-960.log data/logs/rescore-v5-640.log data/logs/rescore-v5-960.log >> $L
echo "rescore done $(date +%H:%M:%S)" >> $L
