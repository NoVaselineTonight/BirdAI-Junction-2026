#!/bin/bash
# laptop: poll the spare accounts and rent every usable GPU machine on offer (spot first, then on demand).
# After a pass that rented something, the machines are set up in the background and this script exits so the session is told.
T=$HOME/WORKDIR; G=$T/grab; MAXPER=${MAXPER:-3}
for round in $(seq 1 2000); do
  got=0
  for p in ACCOUNT_D ACCOUNT_B ACCOUNT_C; do
    have=$(VERDA_PROFILE=$p verda --agent vm list 2>/dev/null | python3 -c "import sys,json; print(len(json.load(sys.stdin) or []))" 2>/dev/null); have=${have:-0}
    for mode in ondemand spot; do
      [ "$have" -ge "$MAXPER" ] && break
      flag=""; [ $mode = spot ] && flag="--spot"
      VERDA_PROFILE=$p verda --agent vm availability --kind gpu $flag 2>/dev/null | python3 -c "
import sys,json,re
try: d=json.load(sys.stdin) or []
except Exception: d=[]
rows=[]
for r in d:
    t=r.get('instance_type',''); m=re.match(r'(\d+)',t); v=re.match(r'(\d+)',str(r.get('vram','0')))
    if not m or not v or 'V100' in t or int(v.group(1))<40: continue
    rows.append((int(m.group(1)), t, r.get('location'), r.get('cpu_cores') or 8))
for n,t,loc,c in sorted(rows, reverse=True): print(n,t,loc,c)" > $G/offers.txt 2>/dev/null
      while read NG TYPE LOC CPUS; do
        [ "$have" -ge "$MAXPER" ] && break
        key="$p/$TYPE/$LOC/$mode"; now=$(date +%s)
        last=$(grep -F "$key " $G/refused.txt 2>/dev/null | tail -1 | awk '{print $2}'); [ -n "$last" ] && [ $((now-last)) -lt 180 ] && continue
        OS=$(VERDA_PROFILE=$p verda --agent images --type $TYPE 2>/dev/null < /dev/null | python3 -c "
import sys,json
l=[r['image_type'] for r in json.load(sys.stdin)]
for w in ('24.04.cuda12.9','24.04.cuda12.8','24.04.cuda13.0','24.04.cuda13.2','24.04.cuda13.4'):
    if w in l: print(w); break" 2>/dev/null)
        [ -n "$OS" ] || continue
        C=$(( $(cat $G/counter) + 1 )); echo $C > $G/counter; NAME=birdai-g$C
        SP=""; [ $mode = spot ] && SP="--is-spot --os-volume-on-spot-discontinue delete_permanently"
        VERDA_PROFILE=$p verda --agent vm create --kind gpu --instance-type $TYPE --location $LOC --os $OS --os-volume-size 120 --hostname $NAME --description "BirdAI: rented by the grabber ($mode, delete after)" --ssh-key $(cat $T/$p-key-id) $SP > $G/create-$NAME.json 2>&1 < /dev/null
        ID=$(python3 -c "
import json
try: print(json.load(open('$G/create-$NAME.json')).get('id') or '')
except Exception: print('')")
        if [ -z "$ID" ] && grep -q "deadline exceeded" $G/create-$NAME.json; then
          # the order timed out; it may still have gone through
          sleep 8
          ID=$(VERDA_PROFILE=$p verda --agent vm list 2>/dev/null < /dev/null | python3 -c "
import sys,json
for v in json.load(sys.stdin) or []:
    if v.get('hostname')=='$NAME': print(v['id'])" 2>/dev/null | head -1)
        fi
        if [ -n "$ID" ]; then
          printf 'PROFILE=%s\nID=%s\nTYPE=%s\nNGPU=%s\nCPUS=%s\nMODE=%s\n' $p $ID $TYPE $NG $CPUS $mode > $G/$NAME.env
          echo "$NAME $p $ID $TYPE $LOC $mode" >> $G/rented.txt
          echo "$(date +%H:%M:%S) RENTED $NAME on $p: $TYPE in $LOC ($mode)"
          setsid nohup bash $G/setup-machine.sh $NAME > /dev/null 2>&1 &
          got=$((got+1)); have=$((have+1))
        else
          echo "$key $now $(tr -d '\n' < $G/create-$NAME.json | cut -c1-160)" >> $G/refused.txt
        fi
      done < $G/offers.txt
    done
  done
  [ $got -gt 0 ] && { echo "$(date +%H:%M:%S) rented $got machine(s) this pass; setup is running in the background"; exit 0; }
  sleep 45
done
