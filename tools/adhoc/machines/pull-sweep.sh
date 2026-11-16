#!/bin/bash
cd ~/birdai
while true; do
  for spec in $(cat data/sweep-machines.txt 2>/dev/null); do
    ip=${spec%%:*}; name=${spec##*:}; mkdir -p data/sweep/$name
    rsync -a -e 'ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new' root@$ip:birdai/data/sweep/$name/scores.log root@$ip:birdai/data/sweep/$name/scored.pt data/sweep/$name/ 2>/dev/null
  done
  sleep 120
done
