#!/usr/bin/env bash
# Stop the accuracy-history run (it is rerun later when the machine is quiet).
for p in $(pgrep -f "history2[.]sh"); do kill "$p" 2>/dev/null; done
for p in $(pgrep -f "curve2[.]py"); do kill "$p" 2>/dev/null; done
sleep 2
echo "history procs left: $(pgrep -f "curve2[.]py" | wc -l)"
