#!/usr/bin/env bash
# Waits for mining to finish, then labels the mined frames and makes the review sheets.
export PATH=$HOME/.local/bin:$PATH
cd ~/birdai
until grep -q "mine exit" data/logs/mine.log 2>/dev/null; do sleep 5; done
if ! grep -q "mine exit 0" data/logs/mine.log; then echo "mining failed, not labelling" > data/logs/label.log; exit 1; fi
echo "label start $(date +%H:%M:%S)" > data/logs/label.log
mkdir -p data/labels
uv run --group train python tools/autolabel.py --frames data/frames --out data/labels/auto.jsonl >> data/logs/label.log 2>&1
echo "autolabel exit $? $(date +%H:%M:%S)" >> data/logs/label.log
uv run --group train python tools/review_sheets.py --labels data/labels/auto.jsonl --frames data/frames --out data/review >> data/logs/label.log 2>&1
echo "sheets exit $? $(date +%H:%M:%S)" >> data/logs/label.log
