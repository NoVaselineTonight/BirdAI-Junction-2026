#!/bin/bash
# main: model-size test on the main machine's own GPU: YOLO26s at 640 px on the checked labels
cd ~/birdai
setsid -f bash data/score_loop.sh s640-main 640 > /dev/null 2>&1
.venv/bin/python data/train_big.py --model yolo26s.pt --imgsz 640 --epochs 16 --batch 64 --workers 22 --name s640-main --device 0 > data/logs/s640-main.log 2>&1
echo "job exit $? $(date +%H:%M:%S)" >> data/logs/s640-main.log
