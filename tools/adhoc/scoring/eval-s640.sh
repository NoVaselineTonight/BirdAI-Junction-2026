#!/bin/bash
# main: export the bigger student (YOLO26s 640) and run the project's selection tool on it:
# cut-off picked on the 13 never-trained days, measured on 12 Nov. Board time is a placeholder until measured.
export PATH=$HOME/.local/bin:$PATH
cd ~/birdai
L=data/logs/eval-s640.log; echo "start $(date +%H:%M:%S)" > $L
M=models_s640; rm -rf $M; mkdir -p $M/student; ln -sfn ../models/pretrained $M/pretrained
.venv/bin/python data/export_pt.py data/sweep/s640-main/t/weights/last.pt yolo26s 640 $M/student 640 >> $L 2>&1
echo "export exit $? $(date +%H:%M:%S)" >> $L
uv run --group train python tools/evaluate.py --dataset data/dataset_v8n --candidates two_stage student:640 \
  --models-dir $M --board-ms two_stage=169.8,640=1499 --promote > data/logs/eval-s640-full.log 2>&1
echo "eval exit $? $(date +%H:%M:%S)" >> $L
grep -a "threshold\|count_exact\|SHIP\|great_tit \|blue_tit \|bullfinch \|magpie \|red_squirrel \|great_spotted" data/logs/eval-s640-full.log | cut -c1-170 >> $L
# the same weights on the 5 exam days (never used for any choice), against the current nano model
for w in data/sweep/s640-main/t/weights/last.pt models/student_v8a_640/runs/640/weights/best.pt data/evo/run1/best-weights.pt; do
  PYTHONPATH=.:tools .venv/bin/python data/evo_one.py --score-only --parent $w --out /tmp/exam-score --fit-dataset data/dataset_exam --fit-split test --val-every 1 2>&1 | grep RESULT | sed "s#^#exam $w #" >> $L
done
echo "done $(date +%H:%M:%S)" >> $L
