#!/bin/bash
# a machine YouTube accepts: download videos and hand each one to the processing machine, then mark the set ready.
# Usage: dl-relay.sh TAG "name:id name:id ..." TARGET_IP
export PATH=$HOME/.local/bin:$PATH
TAG=$1; LIST=$2; IP=$3
mkdir -p ~/relay/$TAG ~/birdai/data/logs; cd ~/relay/$TAG || exit 1
L=~/birdai/data/logs/relay-$TAG.log; echo "relay $TAG start $(date +%H:%M:%S)" > $L
command -v aria2c >/dev/null || { DEBIAN_FRONTEND=noninteractive apt-get update >/dev/null 2>&1; DEBIAN_FRONTEND=noninteractive apt-get install -y aria2 >/dev/null 2>&1; }
R="ssh -i $HOME/.ssh/KEY -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15"
$R root@$IP "mkdir -p ~/birdai/data/videos_$TAG/train"
dl() {
  name=${1%%:*}; id=${1##*:}
  uvx yt-dlp -f "${FMT:-137/136/bv*[height<=1080][ext=mp4]/bv*[height<=1080]}" --downloader aria2c \
    --downloader-args "aria2c:-x 16 -s 16 -k 1M --summary-interval=60 --console-log-level=warn" \
    --retries 20 -o "${PFX-xf-}$name.%(ext)s" "https://www.youtube.com/watch?v=$id" > dl-$name.log 2>&1 < /dev/null
  f=$(ls ${PFX-xf-}$name.* 2>/dev/null | grep -v "\.part\|\.aria2\|\.ytdl" | head -1)
  if [ -n "$f" ]; then
    rsync -a -e "$R" "$f" root@$IP:birdai/data/videos_$TAG/train/ >> $L 2>&1 && echo "$name sent $(du -h "$f" | cut -f1) $(date +%H:%M:%S)" >> $L; rm -f "$f"
  else echo "$name download FAILED: $(tail -1 dl-$name.log | cut -c1-150)" >> $L; fi
}
n=0; for item in $LIST; do dl $item & n=$((n+1)); [ $((n % ${PAR:-4})) = 0 ] && wait; done; wait
$R root@$IP "touch ~/birdai/data/videos_$TAG/READY"
echo "relay $TAG done $(date +%H:%M:%S)" >> $L
