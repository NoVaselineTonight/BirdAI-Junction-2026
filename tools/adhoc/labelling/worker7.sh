#!/usr/bin/env bash
# Worker follow-up with the better teacher: wait for the scan to end, then label at bar 0.05 and embed.
# Usage: bash data/worker7.sh <label name, e.g. auto3> [move_frames_b]
export PATH=$HOME/.local/bin:$PATH
cd ~/birdai || exit 1
N=$1
L=data/logs/worker7.log
echo "worker7 waiting $(date +%H:%M:%S)" > $L
while pgrep -f "tools/mine_frames[.]py" > /dev/null; do sleep 15; done
echo "scan ended $(date +%H:%M:%S)" >> $L
if [ "$2" = "move_frames_b" ]; then mv data/frames_b/train/* data/frames/train/ && echo moved >> $L; fi
ls data/frames/train >> $L
for d in data/frames/train/*; do echo "$d $(ls $d | wc -l)" >> $L; done
uv run --group train python tools/autolabel.py --frames data/frames --out data/labels/$N.jsonl --box-conf 0.05 > data/logs/label-$N.log 2>&1
echo "label exit $? $(date +%H:%M:%S)" >> $L
uv run --group train python data/embed.py data/labels/$N.jsonl data/frames > data/logs/embed-$N.log 2>&1
echo "embed exit $? $(date +%H:%M:%S)" >> $L
