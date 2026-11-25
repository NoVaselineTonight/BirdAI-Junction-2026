#!/usr/bin/env bash
# Main: when teacher 2 is trained on birdai-fast, fetch its weights and hand them to the workers.
cd ~/birdai || exit 1
L=data/logs/get-big2.log
echo "get-big2 waiting $(date +%H:%M:%S)" > $L
until ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15 root@MACHINE_IP 'grep -q "big2 exit 0" ~/birdai/data/logs/fast.log' 2>/dev/null; do sleep 20; done
scp -o ConnectTimeout=15 root@MACHINE_IP:birdai/runs_big/t2/weights/best.pt data/big2.pt.part >> $L 2>&1 && mv data/big2.pt.part data/big2.pt
echo "fetched exit $? $(date +%H:%M:%S)" >> $L
for ip in MACHINE_IP MACHINE_IP; do
  scp -o ConnectTimeout=15 data/big2.pt root@$ip:birdai/data/big2.pt.part >> $L 2>&1 && ssh -o ConnectTimeout=15 root@$ip 'mv ~/birdai/data/big2.pt.part ~/birdai/data/big2.pt' >> $L 2>&1
  echo "weights2 to $ip exit $? $(date +%H:%M:%S)" >> $L
done
