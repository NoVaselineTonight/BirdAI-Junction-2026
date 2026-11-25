#!/usr/bin/env bash
cd ~/birdai || exit 1
mkdir -p data/highlights
ffmpeg -v error -nostdin -y -ss 4028 -i data/videos/train/talvilintulive-20261022.mp4 -t 175 -an -vf scale=-2:720 \
  -c:v libx264 -preset fast -crf 22 -pix_fmt yuv420p -r 30 -movflags +faststart data/highlights/squirrel-22oct-720.mp4 \
  > data/logs/cut-squirrel.log 2>&1
echo "cut exit $? $(date +%H:%M:%S)" >> data/logs/cut-squirrel.log
ls -la data/highlights/squirrel-22oct-720.mp4 >> data/logs/cut-squirrel.log
