#!/usr/bin/env bash
# Download more stream days at 720p.  Usage: bash data/dl8.sh <local|IP> <date> <id> [<date> <id> ...]
# local: the videos land in ~/birdai/data/videos8/train on this machine.
# IP: each video is sent to that machine's ~/birdai/data/videos8/train (for a machine YouTube blocks).
# Ends by writing data/videos8/READY on the machine that holds the videos; worker8.sh waits for it.
export PATH=$HOME/.local/bin:$PATH
DEST=$1; shift
mkdir -p ~/birdai/data/videos8/train ~/birdai/data/videos8x ~/birdai/data/logs
L=~/birdai/data/logs/dl8-$DEST.log
echo "dl8 start $(date +%H:%M:%S) dest $DEST" > $L
dl() {
  if [ "$DEST" = local ]; then cd ~/birdai/data/videos8/train; else cd ~/birdai/data/videos8x; fi
  uvx yt-dlp -f 136 --downloader aria2c \
    --downloader-args "aria2c:-x 16 -s 16 -k 1M --summary-interval=30 --console-log-level=warn" \
    --retries 20 -o "talvilintulive-$1.%(ext)s" "https://www.youtube.com/watch?v=$2" \
    > ~/birdai/data/logs/dl8-$1.log 2>&1 < /dev/null
  if [ ! -f talvilintulive-$1.mp4 ]; then echo "$1 download FAILED $(date +%H:%M:%S)" >> $L; return; fi
  if [ "$DEST" = local ]; then echo "$1 here $(date +%H:%M:%S)" >> $L; return; fi
  ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15 root@$DEST 'mkdir -p ~/birdai/data/videos8/train' >> $L 2>&1
  rsync -a --inplace -e "ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15" talvilintulive-$1.mp4 \
    root@$DEST:birdai/data/videos8/train/ >> $L 2>&1 && rm -f talvilintulive-$1.mp4
  echo "$1 sent exit $? $(date +%H:%M:%S)" >> $L
}
while [ $# -ge 2 ]; do dl "$1" "$2" & shift 2; done
wait
if [ "$DEST" = local ]; then touch ~/birdai/data/videos8/READY; else ssh -o ConnectTimeout=15 root@$DEST 'touch ~/birdai/data/videos8/READY'; fi
echo "dl8 done $(date +%H:%M:%S)" >> $L
