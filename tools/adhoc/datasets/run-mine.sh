#!/usr/bin/env bash
# Waits for the downloads to finish, then mines frames from all videos.
export PATH=$HOME/.local/bin:$PATH
cd ~/birdai
while pgrep -f "bin/[y]t-dlp" >/dev/null || ls data/videos/*/*.part >/dev/null 2>&1; do sleep 10; done
echo "downloads done $(date +%H:%M:%S)" > data/logs/mine.log
ls -la data/videos/train data/videos/demo >> data/logs/mine.log
mkdir -p data/highlights
uv run --group train python tools/mine_frames.py --videos data/videos --out data/frames --workers 24 \
  --highlights data/highlights/demo-highlights.mp4 --highlights-from talvilintulive-20261113 >> data/logs/mine.log 2>&1
echo "mine exit $? $(date +%H:%M:%S)" >> data/logs/mine.log
