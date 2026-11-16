#!/usr/bin/env bash
# Demo reel: two minutes of the held-out day, then the held-out squirrel visit, then the rest of the held-out day.
cd ~/birdai/data/highlights || exit 1
mkdir -p reel
S=feeder-12nov-720.mp4
ffmpeg -v error -nostdin -y -i $S -t 120 -an -c:v libx264 -preset fast -crf 22 -pix_fmt yuv420p -r 30 -movflags +faststart reel/1-feeder-12nov-part1.mp4
ffmpeg -v error -nostdin -y -ss 120 -i $S -an -c:v libx264 -preset fast -crf 22 -pix_fmt yuv420p -r 30 -movflags +faststart reel/3-feeder-12nov-part2.mp4
cp squirrel-22oct-720.mp4 reel/2-squirrel-22oct.mp4
ls -la reel > ../logs/reel.log
for f in reel/*.mp4; do echo "$f $(ffprobe -v error -show_entries format=duration -of csv=p=0 $f)" >> ../logs/reel.log; done
echo "reel done $(date +%H:%M:%S)" >> ../logs/reel.log
