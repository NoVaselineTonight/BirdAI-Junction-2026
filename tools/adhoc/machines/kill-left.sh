#!/usr/bin/env bash
# Stop decoder workers a stopped miner left behind (their parent is gone, so their parent id is 1).
ps -eo pid,ppid,args | awk '$2 == 1 && /multiprocessing[.]spawn|multiprocessing[.]resource_tracker/ {print $1}' | xargs -r kill 2>/dev/null
sleep 2
for p in $(pgrep -f "videos8c/train/talvilintulive"); do kill "$p" 2>/dev/null; done
sleep 1
echo "orphans: $(ps -eo ppid,args | awk '$1 == 1 && /multiprocessing[.]spawn/' | wc -l), ffmpeg: $(pgrep -f "videos8c/train/talvilintulive" | wc -l), training procs: $(ps -eo args | grep -c "[t]rain_student")"
