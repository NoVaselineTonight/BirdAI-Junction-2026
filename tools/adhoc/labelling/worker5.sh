#!/usr/bin/env bash
# Scan worker 4: ten more days at 720p -> mine frames -> teacher labels -> embeddings. All on this machine.
export DEBIAN_FRONTEND=noninteractive
export PATH=$HOME/.local/bin:$PATH
mkdir -p ~/birdai/data/logs ~/birdai/data/videos/train ~/birdai/data/labels ~/birdai/data/check
L=~/birdai/data/logs/worker5.log
echo "worker5 start $(date +%H:%M:%S)" > $L
(apt-get update -qq && apt-get install -y -qq ffmpeg aria2 nodejs) >> $L 2>&1
command -v uv >/dev/null || (curl -LsSf https://astral.sh/uv/install.sh | UV_NO_MODIFY_PATH=1 sh) >> $L 2>&1
echo "tools ready $(date +%H:%M:%S)" >> $L
cd ~/birdai/data/videos || exit 1
dl() {
  uvx yt-dlp -f 136 --downloader aria2c \
    --downloader-args "aria2c:-x 16 -s 16 -k 1M --summary-interval=30 --console-log-level=warn" \
    --retries 20 -o "train/talvilintulive-$1.%(ext)s" "https://www.youtube.com/watch?v=$2" \
    > ../logs/dl-$1.log 2>&1 < /dev/null
}
dl 20261008 3EjwckY0ejE &
dl 20261012 7udKmn7ilrU &
dl 20261015 5UVwXnJwxE8 &
dl 20261018 Khtf-K6C7k4 &
dl 20261020 aakwoKiGfjw &
dl 20261024 dsxr7FjDXSs &
dl 20261026 cmIBh5X9txM &
dl 20261028 qmDva3EHSvk &
dl 20241202 cjDS6DY5LD4 &
dl 20250102 oxJ9rUSxpvk &
cd ~/birdai && uv sync --group train >> $L 2>&1 &
wait
echo "downloads done $(date +%H:%M:%S)" >> $L
ls -la ~/birdai/data/videos/train >> $L
cd ~/birdai || exit 1
nvidia-smi conf-compute -srs 1 >/dev/null 2>&1
uv run --group train python -c "import torch; print('cuda', torch.cuda.is_available())" >> $L 2>&1
uv run --group train python tools/mine_frames.py --videos data/videos --out data/frames --workers 10 > data/logs/mine.log 2>&1
echo "mine exit $? $(date +%H:%M:%S)" >> $L
uv run --group train python tools/autolabel.py --frames data/frames --out data/labels/auto4.jsonl > data/logs/label4.log 2>&1
echo "label exit $? $(date +%H:%M:%S)" >> $L
uv run --group train python data/embed.py data/labels/auto4.jsonl data/frames > data/logs/embed4.log 2>&1
echo "embed exit $? $(date +%H:%M:%S)" >> $L
