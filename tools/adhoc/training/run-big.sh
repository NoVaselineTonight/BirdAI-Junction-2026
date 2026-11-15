#!/usr/bin/env bash
export PATH=$HOME/.local/bin:$PATH
cd ~/birdai || exit 1
echo "big start $(date +%H:%M:%S)" > data/logs/big.log
uv run --group train python data/big_train.py > data/logs/big-train.log 2>&1
echo "big exit $? $(date +%H:%M:%S)" >> data/logs/big.log
ls -la runs_big/t1/weights >> data/logs/big.log 2>&1
