#!/bin/bash
# main: stop sending the big training set to g19 (its disk is needed for videos); the tool push keeps running
pkill -f "push-to.sh MACHINE_I[P]"; pkill -f "push-MACHINE-I[P]-part"; sleep 1; pgrep -af "MACHINE_IP" | cut -c1-110
