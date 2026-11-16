#!/bin/bash
cd ~/birdai
PYTHONPATH=. .venv/bin/python data/fail.py data/dataset_v5 models_v4/student data/fail_v4 0.5 2>&1 | grep -v "Warning\|warn\|INFO" > data/logs/fail-v4.log
echo "fail done $? $(date +%H:%M:%S)" >> data/logs/fail-v4.log
