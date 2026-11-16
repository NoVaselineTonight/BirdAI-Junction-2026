#!/bin/bash
# main: one copy of each evolution run's log, state and best weights (same as one round of pull-best.sh)
cd ~/birdai
for spec in $(cat data/evo-machines.txt 2>/dev/null); do
  ip=${spec%%:*}; run=${spec##*:}
  mkdir -p data/evo/$run
  rsync -a -e 'ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new' root@$ip:birdai/data/evo/$run/evo.log root@$ip:birdai/data/evo/$run/state.json data/evo/$run/ || { echo "$run: copy failed"; continue; }
  w=$(.venv/bin/python -c "import json; print(json.load(open('data/evo/$run/state.json'))['best']['weights'])")
  [ -n "$w" ] && rsync -a -e 'ssh -o ConnectTimeout=10' root@$ip:birdai/$w data/evo/$run/best-weights.pt && echo "$w" > data/evo/$run/best-weights.txt
  echo "$run: $(tail -1 data/evo/$run/evo.log | cut -c1-120) | weights $w $(stat -c %s data/evo/$run/best-weights.pt) bytes"
done
