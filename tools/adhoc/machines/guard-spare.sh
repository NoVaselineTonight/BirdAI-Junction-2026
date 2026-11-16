#!/bin/bash
# laptop: on each spare account, delete all its rented machines when the reported balance is at or under LINE euros
LINE=${LINE:-12}
for i in $(seq 1 3000); do
  for p in team2 team3 team4; do
    B=$(VERDA_PROFILE=$p verda --agent cost balance 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin)['amount'])" 2>/dev/null)
    [ -n "$B" ] || continue
    if python3 -c "import sys; sys.exit(0 if float('$B') <= $LINE else 1)"; then
      for id in $(VERDA_PROFILE=$p verda --agent vm list 2>/dev/null | python3 -c "
import sys,json
for v in json.load(sys.stdin) or []: print(v['id'])"); do
        echo "$(date +%H:%M:%S) $p balance $B <= $LINE: deleting $id"; VERDA_PROFILE=$p verda --agent vm delete $id --with-volumes --yes 2>&1 | tail -1
      done
    fi
  done
  sleep 60
done
