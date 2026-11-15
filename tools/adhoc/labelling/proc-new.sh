#!/bin/bash
# processing machine: download other-feeder footage, pick bird frames, label with the teachers, run the automatic check.
# Usage: proc-new.sh TAG "name:id name:id ..."   (videos are deleted after their frames are picked)
export PATH=$HOME/vlm/bin:$HOME/.local/bin:$PATH
cd ~/birdai
TAG=$1; LIST=$2
L=data/logs/proc-$TAG.log; echo "proc $TAG start $(date +%H:%M:%S)" > $L
if ! command -v aria2c >/dev/null || ! command -v ffmpeg >/dev/null || ! command -v ninja >/dev/null; then
  DEBIAN_FRONTEND=noninteractive apt-get update > data/logs/apt.log 2>&1
  DEBIAN_FRONTEND=noninteractive apt-get install -y ffmpeg aria2 python3.12-dev ninja-build build-essential >> data/logs/apt.log 2>&1
fi
command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh 2>/dev/null | sh > data/logs/uv-install.log 2>&1
export PATH=$HOME/.local/bin:$PATH
echo "tools: ffmpeg $(command -v ffmpeg) aria2c $(command -v aria2c) uv $(command -v uv) $(date +%H:%M:%S)" >> $L
until [ -f ~/proc-assets-done ]; do sleep 5; done
echo "assets here $(date +%H:%M:%S)" >> $L
V=data/videos_$TAG; F=data/frames_$TAG; mkdir -p $V/train data/labels
dl() {
  name=${1%%:*}; id=${1##*:}
  uvx yt-dlp -f "137/136/bv*[height<=1080][ext=mp4]/bv*[height<=1080]" --downloader aria2c \
    --downloader-args "aria2c:-x 16 -s 16 -k 1M --summary-interval=60 --console-log-level=warn" \
    --retries 20 -o "$V/train/xf-$name.%(ext)s" "https://www.youtube.com/watch?v=$id" > data/logs/dl-$name.log 2>&1 < /dev/null
  f=$(ls $V/train/xf-$name.* 2>/dev/null | grep -v "\.part\|\.aria2\|\.ytdl" | head -1)
  if [ -n "$f" ]; then echo "$name ok $(du -h "$f" | cut -f1) $(date +%H:%M:%S)" >> $L; else echo "$name download FAILED: $(tail -1 data/logs/dl-$name.log | cut -c1-160)" >> $L; fi
}
n=0; for item in $LIST; do dl $item & n=$((n+1)); [ $((n % 5)) = 0 ] && wait; done; wait
rm -f $V/train/*.part $V/train/*.aria2 $V/train/*.ytdl
echo "downloads done: $(ls $V/train | wc -l) files, $(du -sh $V | cut -f1) $(date +%H:%M:%S)" >> $L
.venv/bin/python tools/mine_frames.py --videos $V --out $F --workers 18 > data/logs/mine-$TAG.log 2>&1
echo "mine exit $? frames $(find $F -name '*.jpg' | wc -l) $(date +%H:%M:%S)" >> $L
rm -rf $V
.venv/bin/python tools/autolabel.py --frames $F --out data/labels/auto_$TAG.jsonl > data/logs/label-$TAG.log 2>&1
echo "label exit $? rows $(wc -l < data/labels/auto_$TAG.jsonl) $(date +%H:%M:%S)" >> $L
D=data/dataset_$TAG; C=data/check_$TAG; rm -rf $D $C ${D}k
.venv/bin/python data/stage_xf.py $D data/labels/auto_$TAG.jsonl:$F > data/logs/stage-$TAG.log 2>&1
echo "stage exit $? $(ls $D/images/train | wc -l) frames $(date +%H:%M:%S)" >> $L
.venv/bin/python data/cand.py $D train $C > data/logs/cand-$TAG.log 2>&1
echo "cand exit $? $(cat $C/cands-*.jsonl | wc -l) candidates $(date +%H:%M:%S)" >> $L
if ! curl -s -m 3 http://127.0.0.1:8000/v1/models | grep -q Qwen; then
  OMP_NUM_THREADS=1 setsid -f $HOME/vlm/bin/vllm serve Qwen/Qwen3-VL-8B-Instruct --port 8000 --max-model-len 4096 --gpu-memory-utilization 0.45 --limit-mm-per-prompt.video 0 --mm-processor-cache-gb 0 --max-num-seqs 128 > ~/vlm-server.log 2>&1
fi
for i in $(seq 1 180); do curl -s -m 3 http://127.0.0.1:8000/v1/models | grep -q Qwen && break; sleep 5; done
echo "judge server $(curl -s -m 3 http://127.0.0.1:8000/v1/models | grep -q Qwen && echo up || echo NOT UP) $(date +%H:%M:%S)" >> $L
~/vlm/bin/python data/judge.py $C --workers 128 > data/logs/judge-$TAG.log 2>&1
~/vlm/bin/python data/judge.py $C --workers 64 >> data/logs/judge-$TAG.log 2>&1
echo "judged $(wc -l < $C/verdicts.jsonl) $(date +%H:%M:%S)" >> $L
sed 's/stem.startswith("talvilintulive-")/stem.startswith(("talvilintulive-", "xf-"))/' data/truth.py > data/truth_xf.py
OMP_NUM_THREADS=1 .venv/bin/python data/truth_xf.py $D $C ${D}k train --procs 18 > data/logs/truth-$TAG.log 2>&1
echo "truth exit $? kept frames $(ls ${D}k/images/train 2>/dev/null | wc -l) $(date +%H:%M:%S)" >> $L
tail -30 data/logs/truth-$TAG.log >> $L
echo "proc $TAG done $(date +%H:%M:%S)" >> $L
