#!/bin/bash
# main: every 2 minutes copy each evolution run's log, state and best weights here, so a deleted machine loses nothing
cd ~/birdai
while true; do
  for spec in $(cat data/evo-machines.txt 2>/dev/null); do
    ip=${spec%%:*}; run=${spec##*:}
    mkdir -p data/evo/$run
    rsync -a -e 'ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new' root@$ip:birdai/data/evo/$run/evo.log root@$ip:birdai/data/evo/$run/state.json data/evo/$run/ 2>/dev/null || continue
    w=$(.venv/bin/python -c "import json; print(json.load(open('data/evo/$run/state.json'))['best']['weights'])" 2>/dev/null)
    [ -n "$w" ] && rsync -a -e 'ssh -o ConnectTimeout=10' root@$ip:birdai/$w data/evo/$run/best-weights.pt 2>/dev/null && echo "$w" > data/evo/$run/best-weights.txt
  done
  sleep 120
done
