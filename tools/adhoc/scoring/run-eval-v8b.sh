#!/bin/bash
cd ~/birdai
until grep -q "fit done" data/logs/fit.log; do sleep 5; done
bash data/eval-v8.sh
