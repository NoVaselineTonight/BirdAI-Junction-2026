#!/usr/bin/env bash
export PATH=$HOME/.local/bin:$PATH
cd ~/birdai || exit 1
uv run --group train python tools/evaluate.py --dataset data/dataset_v1 --candidates two_stage student:960 --models-dir models_v1 > data/logs/eval-v1.log 2>&1
echo "eval exit $? $(date +%H:%M:%S)" >> data/logs/eval-v1.log
