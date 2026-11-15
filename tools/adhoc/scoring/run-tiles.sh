#!/bin/bash
cd ~/birdai
L=data/logs/tiles.log; : > $L
( TILES=400 PYTHONPATH=. nice .venv/bin/python data/rescore_t.py data/dataset_v5 models_v4/student v4-640-2tiles 2>&1 | grep "^ROW\|great_tit\|blue_tit\|magpie\|Error\|error" > data/logs/tiles-640.log ) &
( TILES=400 PYTHONPATH=. nice .venv/bin/python data/rescore_t.py data/dataset_v5 models_v4/student/960 v4-960-2tiles 2>&1 | grep "^ROW\|great_tit\|blue_tit\|magpie\|Error\|error" > data/logs/tiles-960.log ) &
wait
cat data/logs/tiles-640.log data/logs/tiles-960.log >> $L
echo "tiles done $(date +%H:%M:%S)" >> $L
