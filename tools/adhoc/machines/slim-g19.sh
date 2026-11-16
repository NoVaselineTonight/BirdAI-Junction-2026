#!/bin/bash
# g19: this machine only processes new footage; drop the big training images to make room for videos, stop any search job
cd ~/birdai
pkill -f "data/run-job.s[h]"; pkill -f "data/evolve.p[y]"; pkill -f "data/evo_one.p[y]"
rm -rf data/dataset_v8/images/train data/dataset_v8/labels/train
ls data/dataset_v8; df -h / | tail -1; cat data/logs/proc-d3.log 2>/dev/null; pgrep -af "proc-own|start-own" | grep -v pgrep | cut -c1-80
