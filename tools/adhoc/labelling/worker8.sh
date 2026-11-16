#!/usr/bin/env bash
# One worker's whole chain for the extra days: wait for the videos, mine frames, label at bar 0.05, embed,
# then both in-domain teachers propose missed birds.
# Streams are cut into one-hour pieces before mining (see below).  Usage: bash data/worker8.sh <tag number> <mine workers>
# Reads data/videos8/train/*.mp4, data/big.pt, data/big2.pt.  Writes data/frames8/train/<video>/ and
# data/labels/auto<tag>.jsonl, big<tag>.jsonl, big<tag>b.jsonl (each with .emb.npz).  Log: data/logs/worker8.log
export PATH=$HOME/.local/bin:$PATH
cd ~/birdai || exit 1
N=$1; W=${2:-10}
L=data/logs/worker8.log
echo "worker8 waiting $(date +%H:%M:%S)" > $L
until [ -f data/videos8/READY ]; do sleep 10; done
find data/videos8/train -type f ! -name "*.mp4" -delete
ls -la data/videos8/train >> $L
uv run --group train python -c "import torch; print('cuda', torch.cuda.is_available())" >> $L 2>&1
# The miner decodes one whole video per worker, so each stream is first cut into one-hour pieces (stream copy)
# and the pieces are decoded side by side. Frame names then carry the piece: talvilintulive-<date>-h<NN>_<ms>.jpg
mkdir -p data/videos8c/train
cut_one() {  # the original is deleted once its pieces exist, so the disk never holds much more than one copy
  local s; s=$(basename "$1" .mp4)
  ffmpeg -v error -nostdin -i "$1" -c copy -an -f segment -segment_time 3600 -reset_timestamps 1 \
    "data/videos8c/train/$s-h%02d.mp4" >> $L 2>&1 && rm -f "$1"
  echo "$s cut exit $? $(date +%H:%M:%S)" >> $L
}
n=0
for v in data/videos8/train/*.mp4; do
  cut_one "$v" &
  n=$((n + 1)); [ $((n % 3)) -eq 0 ] && wait
done
wait
echo "pieces: $(ls data/videos8c/train | wc -l)" >> $L
uv run --group train python tools/mine_frames.py --videos data/videos8c --out data/frames8 --workers $W --max-per-video 300 > data/logs/mine8.log 2>&1
echo "mine exit $? $(date +%H:%M:%S)" >> $L
[ -n "$(ls data/frames8/train 2>/dev/null)" ] && rm -rf data/videos8c  # the pieces are no longer needed
for d in data/frames8/train/*; do echo "$d $(ls $d | wc -l)" >> $L; done
uv run --group train python tools/autolabel.py --frames data/frames8 --out data/labels/auto$N.jsonl --box-conf 0.05 > data/logs/label-auto$N.log 2>&1
echo "label exit $? $(date +%H:%M:%S)" >> $L
uv run --group train python data/embed.py data/labels/auto$N.jsonl data/frames8 > data/logs/embed-auto$N.log 2>&1
echo "embed exit $? $(date +%H:%M:%S)" >> $L
uv run --group train python data/big_propose.py data/big.pt data/labels/auto$N.jsonl data/frames8 data/labels/big$N.jsonl > data/logs/propose-big$N.log 2>&1
echo "propose exit $? $(date +%H:%M:%S)" >> $L
uv run --group train python data/embed.py data/labels/big$N.jsonl data/frames8 > data/logs/embed-big$N.log 2>&1
cat data/labels/auto$N.jsonl data/labels/big$N.jsonl > data/labels/_tmp_big${N}b.jsonl
uv run --group train python data/big_propose.py data/big2.pt data/labels/_tmp_big${N}b.jsonl data/frames8 data/labels/big${N}b.jsonl > data/logs/propose-big${N}b.log 2>&1
echo "propose2 exit $? $(date +%H:%M:%S)" >> $L
sed -i 's/#big\([0-9]\)/#bigT2_\1/' data/labels/big${N}b.jsonl   # ids must not collide with the first round's
uv run --group train python data/embed.py data/labels/big${N}b.jsonl data/frames8 > data/logs/embed-big${N}b.log 2>&1
echo "worker8 done $(date +%H:%M:%S)" >> $L
