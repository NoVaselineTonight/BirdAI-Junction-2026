#!/usr/bin/env bash
# Give the accuracy-history run the lowest priority so it does not slow the dataset build or the promotion.
for p in $(pgrep -f "history2[.]sh") $(pgrep -f "curve2[.]py"); do renice -n 19 -p "$p" > /dev/null && echo "niced $p"; done
