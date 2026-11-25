#!/bin/bash
# processing machine: when the two-day batch d3 is through, process batch d4 (videos arrive as streams)
cd ~/birdai
until grep -q "proc-own d3 done" data/logs/proc-d3.log 2>/dev/null; do sleep 15; done
bash data/proc-own2.sh d4
