#!/bin/bash
# main: save what exists only on the rented training / footage machines to the store machine (ACCOUNT_D)
G18=MACHINE_IP; G13=MACHINE_IP; ST=MACHINE_IP; L=~/birdai/data/logs/save-round2.log; echo "save start $(date +%H:%M:%S)" > $L
R="ssh -o ConnectTimeout=15 -o StrictHostKeyChecking=accept-new"
$R root@$ST 'mkdir -p ~/birdai/data/from_g18 ~/birdai/data/from_g13'
$R root@$G18 'cd ~/birdai/data && tar -cf - dataset_x2k check_x2/verdicts.jsonl v9runs/*/t/weights/last.pt v9runs/*/t/results.csv logs/v9.log logs/v10.log logs/snap-*.log run-v9.sh run-v9c.sh run-v10.sh train_v9.py train_v10.py' | $R root@$ST 'tar -C ~/birdai/data/from_g18 -xf -'; echo "g18 exit ${PIPESTATUS[*]} $(date +%H:%M:%S)" >> $L
$R root@$G13 'cd ~/birdai/data && tar -cf - dataset_xf1k dataset_xf2k check_xf1/verdicts.jsonl check_xf2/verdicts.jsonl labels/auto_xf1.jsonl labels/auto_xf2.jsonl logs/proc-xf1.log logs/proc-xf2.log 2>/dev/null' | $R root@$ST 'tar -C ~/birdai/data/from_g13 -xf -'; echo "g13 exit ${PIPESTATUS[*]} $(date +%H:%M:%S)" >> $L
$R root@$ST 'cd ~/birdai/data; for d in from_g18/dataset_x2k from_g13/dataset_xf1k from_g13/dataset_xf2k; do echo "$d images $(ls $d/images/train | wc -l) labels $(ls $d/labels/train | wc -l)"; done; ls from_g18/v9runs; du -sh from_g18 from_g13 | tr "\n" " "' >> $L 2>&1
# small things also to main itself (weights and logs)
mkdir -p ~/birdai/data/v9keep; for n in v9_960_e14 v10_960_e8 v9_s640_e8 v9_960_e8_seed1; do scp -q -o ConnectTimeout=15 root@$G18:birdai/data/v9runs/$n/t/weights/last.pt ~/birdai/data/v9keep/$n.pt; done
scp -q root@$G18:birdai/data/logs/v9.log root@$G18:birdai/data/logs/v10.log ~/birdai/data/v9keep/
echo "save done $(date +%H:%M:%S)" >> $L
