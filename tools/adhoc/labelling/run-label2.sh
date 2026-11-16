#!/usr/bin/env bash
# Main machine: when the 9-11 Nov scan ends, label those frames with the teachers and embed them.
export PATH=$HOME/.local/bin:$PATH
cd ~/birdai || exit 1
L=data/logs/label2-run.log
echo "waiting $(date +%H:%M:%S)" > $L
until grep -q "mine2 exit" data/logs/mine2.log 2>/dev/null; do sleep 15; done
grep "mine2 exit" data/logs/mine2.log >> $L
uv run --group train python tools/autolabel.py --frames data/frames2 --out data/labels/auto2.jsonl > data/logs/label2.log 2>&1
echo "label exit $? $(date +%H:%M:%S)" >> $L
uv run --group train python data/embed.py data/labels/auto2.jsonl data/frames2 > data/logs/embed2.log 2>&1
echo "embed exit $? $(date +%H:%M:%S)" >> $L
