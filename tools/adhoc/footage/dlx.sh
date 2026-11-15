#!/usr/bin/env bash
# On scan3: download ten more days and hand each one to scan4 (YouTube blocks scan4's address).
export PATH=$HOME/.local/bin:$PATH
mkdir -p ~/birdai/data/videos_x ~/birdai/data/logs
cd ~/birdai/data/videos_x || exit 1
L=~/birdai/data/logs/dlx.log
echo "dlx start $(date +%H:%M:%S)" > $L
dl() {
  uvx yt-dlp -f 136 --downloader aria2c \
    --downloader-args "aria2c:-x 16 -s 16 -k 1M --summary-interval=30 --console-log-level=warn" \
    --retries 20 -o "talvilintulive-$1.%(ext)s" "https://www.youtube.com/watch?v=$2" \
    > ../logs/dlx-$1.log 2>&1 < /dev/null
  if [ -f talvilintulive-$1.mp4 ]; then
    rsync -a --inplace -e "ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15" talvilintulive-$1.mp4 \
      root@MACHINE_IP:birdai/data/videos/train/ >> $L 2>&1 && rm -f talvilintulive-$1.mp4
    echo "$1 sent exit $? $(date +%H:%M:%S)" >> $L
  else
    echo "$1 download FAILED $(date +%H:%M:%S)" >> $L
  fi
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
wait
ssh -o ConnectTimeout=15 root@MACHINE_IP 'touch ~/birdai/data/videos/READY'
echo "dlx done $(date +%H:%M:%S)" >> $L
