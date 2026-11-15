#!/usr/bin/env bash
# Main machine: relabel its frames with the teacher detector at a lower bar (0.05), then embed. Squirrel frame
# folders are moved aside meanwhile so the bird teacher does not label them.
export PATH=$HOME/.local/bin:$PATH
cd ~/birdai || exit 1
L=data/logs/relabel-main.log
echo "start $(date +%H:%M:%S)" > $L
mkdir -p data/frames_sq
for d in sqphoto orava-1h synth-squirrel; do [ -d data/frames/train/$d ] && mv data/frames/train/$d data/frames_sq/; done
( uv run --group train python tools/autolabel.py --frames data/frames --out data/labels/autoB.jsonl --box-conf 0.05 > data/logs/labelB.log 2>&1
  echo "labelB exit $? $(date +%H:%M:%S)" >> $L
  uv run --group train python data/embed.py data/labels/autoB.jsonl data/frames > data/logs/embedB.log 2>&1
  echo "embedB exit $? $(date +%H:%M:%S)" >> $L ) &
( uv run --group train python tools/autolabel.py --frames data/frames2 --out data/labels/auto2B.jsonl --box-conf 0.05 > data/logs/label2B.log 2>&1
  echo "label2B exit $? $(date +%H:%M:%S)" >> $L
  uv run --group train python data/embed.py data/labels/auto2B.jsonl data/frames2 > data/logs/embed2B.log 2>&1
  echo "embed2B exit $? $(date +%H:%M:%S)" >> $L ) &
wait
for d in sqphoto orava-1h synth-squirrel; do [ -d data/frames_sq/$d ] && mv data/frames_sq/$d data/frames/train/; done
echo "all done $(date +%H:%M:%S)" >> $L
