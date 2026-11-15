#!/usr/bin/env bash
cd ~/birdai || exit 1
du -sh data/dataset_v2a > data/logs/push-v2a.log
rsync -a -e "ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15" data/dataset_v2a root@MACHINE_IP:birdai/data/ >> data/logs/push-v2a.log 2>&1
echo "push exit $? $(date +%H:%M:%S)" >> data/logs/push-v2a.log
ssh -o ConnectTimeout=15 root@MACHINE_IP 'touch ~/birdai/data/dataset_v2a.READY' >> data/logs/push-v2a.log 2>&1
