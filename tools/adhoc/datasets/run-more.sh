#!/usr/bin/env bash
# Downloads three more November days and mines them into data/frames2 (training only).
export PATH=$HOME/.local/bin:$PATH
mkdir -p ~/birdai/data/videos2/train ~/birdai/data/frames2
cd ~/birdai/data/videos2 || exit 1
dl() {
  uvx yt-dlp -f 137 --downloader aria2c \
    --downloader-args "aria2c:-x 16 -s 16 -k 1M --summary-interval=30 --console-log-level=warn" \
    --retries 20 -o "train/talvilintulive-$1.%(ext)s" "https://www.youtube.com/watch?v=$2" \
    > ../logs/dl-$1.log 2>&1 < /dev/null
}
dl 20261109 XSpyNkPIJNo &
dl 20261110 hDwP_7w1cVU &
dl 20261111 Tqs56epkqEg &
wait
echo "downloads2 done $(date +%H:%M:%S)" > ../logs/mine2.log
ls -la train >> ../logs/mine2.log
cd ~/birdai || exit 1
uv run --group train python tools/mine_frames.py --videos data/videos2 --out data/frames2 --workers 6 >> data/logs/mine2.log 2>&1
echo "mine2 exit $? $(date +%H:%M:%S)" >> data/logs/mine2.log
