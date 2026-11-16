#!/bin/bash
# laptop: what is rented on which account right now, with balances and the latest job lines
T=$HOME/WORKDIR
echo "== $(date +%H:%M:%S)"
for p in default team2 team3 team4; do
  B=$(VERDA_PROFILE=$p verda --agent cost balance 2>/dev/null | python3 -c "import sys,json; print(round(json.load(sys.stdin)['amount'],2))" 2>/dev/null)
  echo "-- $p balance ${B:-?}"
  VERDA_PROFILE=$p verda --agent vm list 2>/dev/null | python3 -c "
import sys,json
d=json.load(sys.stdin) or []
for v in d:
    g=v.get('gpu') or {}; print('  ', v.get('hostname'), v.get('status'), '|', g.get('description'), '|', (v.get('gpu_memory') or {}).get('size_in_gigabytes'), 'GB VRAM |', (v.get('memory') or {}).get('size_in_gigabytes'), 'GB RAM |', (v.get('cpu') or {}).get('number_of_cores'), 'CPU |', round(v.get('price_per_hour') or 0,2), 'EUR/h', 'spot' if v.get('is_spot') else 'on-demand', '|', v.get('ip'))
if not d: print('   no machines')" 2>/dev/null
done
echo "-- grabber"; tail -2 $T/grab/rented.txt 2>/dev/null; for f in $T/grab/birdai-g*.log; do [ -f "$f" ] && tail -1 "$f" | cut -c1-160; done; echo "refusals: $(wc -l < $T/grab/refused.txt 2>/dev/null || echo 0)"
echo "-- jobs (main machine's copies)"
timeout 40 ssh -i ~/.ssh/KEY -o ConnectTimeout=15 birdai-verda 'cd ~/birdai; for r in data/evo/*/; do [ -f $r/evo.log ] && echo "$(basename $r): $(grep "gen [0-9]*:" $r/evo.log | tail -1 | cut -c1-150)"; done; for s in data/sweep/*/; do [ -f $s/scores.log ] && echo "$(basename $s): $(tail -1 $s/scores.log | cut -c1-150)"; done; tail -c 200 data/logs/s640-main.log 2>/dev/null | tr "\r" "\n" | tail -1 | cut -c1-110; nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader' 2>&1
