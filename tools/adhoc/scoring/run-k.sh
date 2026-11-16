#!/bin/bash
cd ~/birdai
: > data/logs/k.log
for spec in "models_v4/student v4-640" "models_v4/student/960 v4-960" "models_v5/student/960 v5-960"; do set -- $spec
  ( PYTHONPATH=. nice .venv/bin/python data/rescore.py data/dataset_v5k $1 $2 2>&1 | grep "labels-as-is\|birds [0-9]" > data/logs/k-$2.log ) &
done
wait
cat data/logs/k-v4-640.log data/logs/k-v4-960.log data/logs/k-v5-960.log >> data/logs/k.log
echo "k done $(date +%H:%M:%S)" >> data/logs/k.log
