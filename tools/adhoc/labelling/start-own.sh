#!/bin/bash
# wait until the automatic setup has delivered the code, then start the own-camera processing
cd ~/birdai 2>/dev/null || exit 1
until [ -x .venv/bin/python ] && [ -f tools/mine_frames.py ]; do sleep 10; done
setsid -f bash data/proc-own.sh d3 > /dev/null 2>&1
