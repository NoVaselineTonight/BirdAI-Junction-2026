#!/bin/bash
# main: official selection for the 38-day models: cut-off picked on the 13 selection days (dataset_v8n val), measured on 12 Nov
export PATH=$HOME/.local/bin:$PATH
cd ~/birdai
L=data/logs/eval-v9.log; echo "start $(date +%H:%M:%S)" > $L
M=models_v9; rm -rf $M; mkdir -p $M/student; ln -sfn ../models/pretrained $M/pretrained
.venv/bin/python data/export_pt.py data/v9keep/v9_960_e8.pt yolo26n 960 $M/student 960 >> data/logs/eval-v9-export.log 2>&1; echo "export 960 exit $?" >> $L
.venv/bin/python data/export_pt.py data/v9keep/v9_640_e8.pt yolo26n 640 $M/student 640 >> data/logs/eval-v9-export.log 2>&1; echo "export 640 exit $?" >> $L
uv run --group train python tools/evaluate.py --dataset data/dataset_v8n --candidates two_stage student:640 student:960 \
  --models-dir $M --board-ms two_stage=169.8,960=1111.1,640=510.6 --promote > data/logs/eval-v9-full.log 2>&1
echo "eval exit $? $(date +%H:%M:%S)" >> $L
grep -a "threshold\|count_exact\|SHIP\|great_tit \|blue_tit \|bullfinch \|magpie \|red_squirrel \|great_spotted\|tree_sparrow \|jay " data/logs/eval-v9-full.log | cut -c1-170 >> $L
echo "done $(date +%H:%M:%S)" >> $L
