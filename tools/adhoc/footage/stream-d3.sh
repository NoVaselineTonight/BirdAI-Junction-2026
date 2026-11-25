#!/bin/bash
# main machine (YouTube accepts it): stream each day's video straight through to the processing machine, nothing stored here.
# Usage: stream-d3.sh TARGET_IP "name:id ..."   (at most 3 at once; waits for free disk on the target)
export PATH=$HOME/.local/bin:$PATH
IP=$1; LIST=$2; L=~/birdai/data/logs/stream-d3.log; echo "stream start $(date +%H:%M:%S)" > $L
R="ssh -o ConnectTimeout=15 -o StrictHostKeyChecking=accept-new -o ServerAliveInterval=30"
one() {
  name=${1%%:*}; id=${1##*:}
  uvx yt-dlp -q -f 136 --http-chunk-size 10M --retries 20 -o - "https://www.youtube.com/watch?v=$id" 2> ~/birdai/data/logs/stream-$name.err \
    | $R root@$IP "cat > ~/birdai/data/videos_d3/.in-$name.mp4"
  rc=${PIPESTATUS[0]}
  if [ $rc = 0 ]; then $R root@$IP "mv ~/birdai/data/videos_d3/.in-$name.mp4 ~/birdai/data/videos_d3/train/$name.mp4; du -h ~/birdai/data/videos_d3/train/$name.mp4 | cut -f1" | sed "s#^#$name sent #; s#\$# $(date +%H:%M:%S)#" >> $L
  else $R root@$IP "rm -f ~/birdai/data/videos_d3/.in-$name.mp4"; echo "$name FAILED exit $rc: $(tail -1 ~/birdai/data/logs/stream-$name.err | cut -c1-120) $(date +%H:%M:%S)" >> $L; fi
}
$R root@$IP "rm -f ~/birdai/data/videos_d3/READY"
for item in $LIST; do
  while true; do
    act=$(jobs -rp | wc -l); free=$($R root@$IP "df -BG --output=avail / | tail -1 | tr -dc 0-9")
    [ "$act" -lt 3 ] && [ "${free:-0}" -ge $((9 * (act + 1) + 8)) ] && break
    sleep 20
  done
  one $item & sleep 5
done
wait
$R root@$IP "touch ~/birdai/data/videos_d3/READY"
echo "stream done $(date +%H:%M:%S)" >> $L
