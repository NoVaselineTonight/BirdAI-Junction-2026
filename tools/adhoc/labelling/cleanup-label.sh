#!/usr/bin/env bash
# Stops every labelling/embedding run and its follow-up script on this machine.
pkill -f "data/worker7[.]sh"
pkill -f "tools/autolabel[.]py"
pkill -f "data/embed[.]py"
sleep 3
echo "left: $(ps -eo args | grep -c 'tools/[a]utolabel\|data/[w]orker7')"
rm -f ~/birdai/data/labels/auto3.jsonl* ~/birdai/data/labels/auto4.jsonl*
