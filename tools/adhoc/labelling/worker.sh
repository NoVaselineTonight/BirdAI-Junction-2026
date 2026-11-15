#!/usr/bin/env bash
# Scan worker: installs what it needs, downloads eight more days at 720p and mines training frames.
export DEBIAN_FRONTEND=noninteractive
export PATH=$HOME/.local/bin:$PATH
mkdir -p ~/birdai/data/logs ~/birdai/data/videos/train
L=~/birdai/data/logs/worker.log
echo "worker start $(date +%H:%M:%S)" > $L
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
dl 20261029 uMWq03IRYsQ &
dl 20261031 lLR8uKZtInk &
dl 20261101 Wr9n_mSmZVY &
dl 20261102 IpTnILIwiD0 &
dl 20261103 d6l2kIRk2Dc &
dl 20261104 uktGwT-KjtY &
dl 20261106 VWQc-UwoPkU &
dl 20261108 _YUHd49IuNc &
wait
echo "downloads done $(date +%H:%M:%S)" >> $L
ls -la train >> $L
cd ~/birdai || exit 1
uv run --group train python tools/mine_frames.py --videos data/videos --out data/frames --workers 12 >> data/logs/mine.log 2>&1
echo "mine exit $? $(date +%H:%M:%S)" >> $L
