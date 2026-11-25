#!/usr/bin/env bash
export PATH=$HOME/.local/bin:$PATH
cd ~/birdai || exit 1
rm -rf data/squirrel_cut data/frames/train/sqphoto data/frames/train/orava-1h
n=$(ls data/squirrel_src/orava_frames 2>/dev/null | wc -l)
[ "$n" -lt 1500 ] && rm -rf data/squirrel_src/orava_frames
uv run --group train python data/squirrel_cut.py > data/logs/squirrel_cut.log 2>&1
