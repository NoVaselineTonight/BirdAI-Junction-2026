#!/bin/bash
# Keeps http://localhost:8088 on this PC pointing at the demo page on the Arduino UNO Q.
# Over Wi-Fi it uses an SSH tunnel; with the USB cable it uses adb. It reconnects by itself.
BOARD="${BIRDAI_BOARD:-}"; KEY="${BIRDAI_KEY:-$HOME/.ssh/id_ed25519}"
[ -n "$BOARD" ] || { echo "set BIRDAI_BOARD to the board's address, e.g. root@192.168.1.50" >&2; exit 1; }
while true; do
  if timeout 6 ssh -i "$KEY" -o ConnectTimeout=4 -o BatchMode=yes "$BOARD" true 2>/dev/null; then
    echo "$(date +%H:%M:%S) board on Wi-Fi: tunnel up"
    ssh -i "$KEY" -N -o BatchMode=yes -o ExitOnForwardFailure=yes -o ServerAliveInterval=5 -o ServerAliveCountMax=2 \
        -L 8088:localhost:8088 "$BOARD" 2>/dev/null
    echo "$(date +%H:%M:%S) tunnel down"
  elif [ "$(adb get-state 2>/dev/null)" = device ]; then
    echo "$(date +%H:%M:%S) board on USB: forward up"
    adb forward tcp:8088 tcp:8088 >/dev/null
    while [ "$(adb get-state 2>/dev/null)" = device ]; do sleep 3; done
    adb forward --remove tcp:8088 2>/dev/null
    echo "$(date +%H:%M:%S) USB gone"
  fi
  sleep 3
done
