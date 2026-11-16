#!/bin/bash
# processing machine: when wave xf1 is through, process wave xf2 (videos arrive by relay)
cd ~/birdai
until grep -q "proc xf1 done" data/logs/proc-xf1.log 2>/dev/null; do sleep 15; done
RELAY=1 bash data/proc-new.sh xf2 relayed
