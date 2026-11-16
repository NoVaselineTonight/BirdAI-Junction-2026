#!/usr/bin/env bash
# Stop the extra-days worker chain and its miner on this machine (training is not touched).
for p in $(pgrep -f "data/worker[8][.]sh"); do kill "$p" 2>/dev/null && echo "killed chain $p"; done
for p in $(pgrep -f "tools/mine_frames[.]py"); do kill "$p" 2>/dev/null && echo "killed miner $p"; done
sleep 3
for p in $(pgrep -f "videos8c/train/talvilintulive"); do kill "$p" 2>/dev/null; done
sleep 1
echo "miners left: $(pgrep -f "tools/mine_frames[.]py" | wc -l), ffmpeg left: $(pgrep -f "videos8c/train/talvilintulive" | wc -l)"
