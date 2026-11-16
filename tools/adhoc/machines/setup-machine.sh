#!/bin/bash
# laptop: bring one freshly rented machine to a running job. Usage: setup-machine.sh NAME
# reads grab/NAME.env (PROFILE ID TYPE NGPU CPUS); writes grab/NAME.log; last line is "SETUP OK ..." or "SETUP FAILED ..."
T=$HOME/WORKDIR; G=$T/grab; NAME=$1; . $G/$NAME.env
K="-i $HOME/.ssh/KEY -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=$G/known_hosts -o ConnectTimeout=10"
say() { echo "$(date +%H:%M:%S) $*" >> $G/$NAME.log; }
fail() { say "SETUP FAILED $NAME: $*"; exit 1; }
say "setup start $NAME $PROFILE $TYPE ngpu $NGPU cpus $CPUS id $ID"
IP=""
for i in $(seq 1 90); do
  J=$(VERDA_PROFILE=$PROFILE verda --agent vm describe $ID 2>/dev/null | python3 -c "
import sys,json
d=json.load(sys.stdin); print(d.get('ip'), d.get('status'))" 2>/dev/null); set -- $J
  case "$2" in discontinued|error|deleted) fail "status $2 before boot";; esac
  [ "$2" = "running" ] && [ -n "$1" ] && [ "$1" != "None" ] && { IP=$1; break; }
  sleep 8
done
[ -n "$IP" ] || fail "never reached running"
echo "IP=$IP" >> $G/$NAME.env; say "running at $IP"
ok=0; for i in $(seq 1 110); do ssh $K root@$IP 'nvidia-smi --query-gpu=name --format=csv,noheader | head -1' >> $G/$NAME.log 2>/dev/null && { ok=1; break; }; sleep 8; done
[ $ok = 1 ] || fail "ssh never answered"
PUB=$(timeout 20 ssh -o ConnectTimeout=10 birdai-verda 'cat ~/.ssh/id_ed25519.pub 2>/dev/null || cat ~/.ssh/id_rsa.pub')
ssh $K root@$IP "echo '$PUB' >> ~/.ssh/authorized_keys; mkdir -p ~/birdai/data/logs" || fail "could not add the main machine's key"
TAG=$(echo $IP | tr . -)
timeout 60 ssh -o ConnectTimeout=15 birdai-verda "cd ~/birdai; setsid -f bash data/push-to.sh $IP > /dev/null 2>&1; echo started" >> $G/$NAME.log 2>&1
ok=0; for i in $(seq 1 240); do o=$(timeout 25 ssh -o ConnectTimeout=15 birdai-verda "grep -c 'push done' ~/birdai/data/logs/push-$TAG.log" 2>/dev/null); [ "${o:-0}" -ge 1 ] && { ok=1; break; }
  if [ $((i % 6)) = 0 ]; then st=$(VERDA_PROFILE=$PROFILE verda --agent vm describe $ID 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('status'))" 2>/dev/null); [ "$st" = "discontinued" ] && fail "taken back by Verda during the data push"; fi
  sleep 10; done
[ $ok = 1 ] || fail "data push did not finish in 40 minutes"
say "data pushed"
N=$(ssh $K root@$IP 'cd ~/birdai; [ -d data/dataset_v8/images/val ] || { cp -al data/dataset_v8/images/test data/dataset_v8/images/val; cp -a data/dataset_v8/labels/test data/dataset_v8/labels/val; }; ls data/dataset_v8/images/train | wc -l')
[ "${N:-0}" -ge 61000 ] || fail "training set incomplete on the machine: $N frames"
JOB=""
if [ "$NGPU" -lt 4 ]; then
  JOB=$( ( flock 9; head -1 $G/sweep-queue.txt; sed -i 1d $G/sweep-queue.txt ) 9> $G/queue.lock )
fi
if [ -n "$JOB" ]; then
  set -- $JOB; MODEL=$1; IMGSZ=$2; EPOCHS=$3; BATCH=$4
  DEV=$(seq -s, 0 $((NGPU-1))); W=$((CPUS-4)); [ $W -gt 24 ] && W=24; BATCH=$((BATCH*NGPU))
  ssh $K root@$IP "cd ~/birdai; cat > data/run-job.sh <<JOBEOF
#!/bin/bash
cd ~/birdai
setsid -f bash data/score_loop.sh $NAME $IMGSZ > /dev/null 2>&1
.venv/bin/python data/train_big.py --model $MODEL --imgsz $IMGSZ --epochs $EPOCHS --batch $BATCH --workers $W --name $NAME --device $DEV > data/logs/job.log 2>&1
echo \"job exit \\\$? \\\$(date +%H:%M:%S)\" >> data/logs/job.log
JOBEOF
chmod +x data/run-job.sh; setsid -f bash data/run-job.sh > /dev/null 2>&1" || fail "could not start the size test"
  timeout 30 ssh -o ConnectTimeout=15 birdai-verda "echo $IP:$NAME >> ~/birdai/data/sweep-machines.txt"
  echo "JOB='size test $MODEL $IMGSZ px $EPOCHS epochs'" >> $G/$NAME.env
  say "SETUP OK $NAME $IP: size test $MODEL at $IMGSZ px, $EPOCHS epochs, $NGPU GPU(s)"
else
  PER=2; [ "$NGPU" -lt 4 ] && PER=3
  W=$(( CPUS / (NGPU*PER) - 1 )); [ $W -gt 12 ] && W=12; [ $W -lt 3 ] && W=3
  GP=$(seq -s, 0 $((NGPU-1))); RUN=run-$NAME; SEED=$(( $(date +%s) % 1000 ))
  ssh $K root@$IP "cd ~/birdai; cat > data/run-job.sh <<JOBEOF
#!/bin/bash
cd ~/birdai
.venv/bin/python data/evolve.py --root data/evo/$RUN --start data/seed.pt --gpus $GP --per-gpu $PER --generations 300 --workers $W --seed $SEED --fit-dataset data/dataset_fit --fit-split test --val-every 2 > data/logs/job.log 2>&1
echo \"job exit \\\$? \\\$(date +%H:%M:%S)\" >> data/logs/job.log
JOBEOF
chmod +x data/run-job.sh; setsid -f bash data/run-job.sh > /dev/null 2>&1" || fail "could not start the evolution run"
  timeout 30 ssh -o ConnectTimeout=15 birdai-verda "echo $IP:$RUN >> ~/birdai/data/evo-machines.txt"
  echo "JOB='evolution $RUN, $((NGPU*PER)) variants'" >> $G/$NAME.env
  say "SETUP OK $NAME $IP: evolution $RUN, $((NGPU*PER)) variants on $NGPU GPU(s)"
fi
