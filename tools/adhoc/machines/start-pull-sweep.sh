#!/bin/bash
cd ~/birdai
setsid -f bash data/pull-sweep.sh >/dev/null 2>&1
