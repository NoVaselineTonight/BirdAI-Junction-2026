#!/bin/bash
# main: export the bigger student (YOLO26s 640) and run the project's selection tool on it:
# cut-off picked on the 13 never-trained days, measured on 12 Nov. Board time is a placeholder until measured.
export PATH=$HOME/.local/bin:$PATH
cd ~/birdai
L=data/logs/eval-s640b.log; echo "start $(date +%H:%M:%S)" > $L
M=models_s640b; rm -rf $M; mkdir -p $M/student; ln -sfn ../models/pretrained $M/pretrained
.venv/bin/python data/export_pt.py data/sweep/birdai-g12/scored.pt yolo26s 640 $M/student 640 >> $L 2>&1
echo "export exit $? $(date +%H:%M:%S)" >> $L
uv run --group train python tools/evaluate.py --dataset data/dataset_v8n --candidates two_stage student:640 \
  --models-dir $M --board-ms two_stage=169.8,640=1479.4 --promote > data/logs/eval-s640b-full.log 2>&1
echo "eval exit $? $(date +%H:%M:%S)" >> $L
grep -a "threshold\|count_exact\|SHIP\|great_tit \|blue_tit \|bullfinch \|magpie \|red_squirrel \|great_spotted" data/logs/eval-s640b-full.log | cut -c1-170 >> $L
# the same weights on the 5 exam days (never used for any choice), against the current nano model
echo "done $(date +%H:%M:%S)" >> $L
