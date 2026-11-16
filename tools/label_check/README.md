# Label check scripts (one-off)

These five scripts made the machine-checked labels of 15 November 2026. They are kept as a record, copied unchanged from the rented GPU machines. They are one-off scripts with hard-coded paths for those machines, they are not tested, and they are not part of the `feeder_census` package. Each script's own docstring says how it was called.

Order the labels were made in:

1. `cand.py`: for every frame, pools boxes from the old label (minus boxes too big to be one small bird), three earlier students and the camera-tuned teacher, and merges the boxes of one bird into one candidate with a crop.
2. `judge.py`: asks the vision-language model (Qwen3-VL-8B-Instruct, served with vLLM) a closed question about every crop and writes its verdicts.
3. `truth.py`: turns candidates and verdicts into labels: a bird needs two agreeing votes on the species; the rest become ignore zones or are dropped. In training frames the ignore zones are blurred out.

The other two were not part of making the labels:

- `rescore.py`: scores a student against the old labels with double boxes merged and oversized boxes ignored (the cross-check against the old labels).
- `clean_labels.py`: the earlier experiment that removed double and oversized boxes from the old training labels by rule; re-training on that did not help.
