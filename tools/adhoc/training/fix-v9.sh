#!/bin/bash
cd ~/birdai
pkill -f "data/run-v9.s[h]"; pkill -f "vllm[ ]serve"
DEBIAN_FRONTEND=noninteractive apt-get update > data/logs/apt.log 2>&1
DEBIAN_FRONTEND=noninteractive apt-get install -y python3.12-dev ninja-build build-essential >> data/logs/apt.log 2>&1
ls /usr/include/python3.12/Python.h || { echo "headers still missing"; exit 1; }
{ sed -n '1,5p' data/run-v9.sh
  echo 'L=data/logs/v9.log; D=data/dataset_x2; C=data/check_x2; echo "restart from the judge step $(date +%H:%M:%S)" >> $L'
  sed -n '15,$p' data/run-v9.sh; } > data/run-v9b.sh
sed -n '6,8p' data/run-v9b.sh | cut -c1-160
setsid -f bash data/run-v9b.sh > data/logs/run-v9b.out 2>&1 < /dev/null
sleep 2; pgrep -f "data/run-v9b.s[h]" | head -2
