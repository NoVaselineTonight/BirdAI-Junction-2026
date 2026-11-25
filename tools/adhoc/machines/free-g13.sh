#!/bin/bash
# g13: stop the automatically started training so the machine is free for footage processing
pkill -f "data/run-job.s[h]"; pkill -f "data/train_big.p[y]"; pkill -f "data/score_loop.s[h]"; sleep 2
pgrep -af "train_big|score_loop|evolve" | grep -v pgrep | cut -c1-80; nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader; df -h / | tail -1
