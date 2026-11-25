"""Teacher labelling: a big YOLO draws the bird boxes, two classifiers name each crop.

    python tools/autolabel.py --frames data/frames --out data/labels/auto.jsonl \
        [--box-model yolo26x.pt] [--imgsz 1280] [--box-conf 0.20]

Runs on the GPU machine under `uv run --group train`. Writes one JSON line per box; a frame
without a bird gets a single "empty" line so empty feeders become training negatives.
"""

import argparse
import json
import math
import sys
from collections import Counter
from collections.abc import Callable, Sequence
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # `python tools/autolabel.py` has no repo root on the path

from feeder_census.species import Species, load_species  # noqa: E402
from feeder_census.types import UNIDENTIFIED  # noqa: E402

COCO_BIRD = 14
FALLBACK_BOX_MODEL = "yolo11x.pt"
BIOCLIP_MODEL = "hf-hub:imageomics/bioclip-2"  # BioCLIP 2; pybioclip 2.1.6 also defaults to it, v1 is "hf-hub:imageomics/bioclip"
INAT_MODEL = Path("models/pretrained/inat_bird.tflite")
INAT_LABELS = Path("models/pretrained/inat_bird_labels.txt")

AUTO_SCORE, AUTO_MARGIN = 0.60, 0.20
SINGLE_SCORE, SINGLE_MARGIN = 0.85, 0.30


def decide_label(bioclip_species: str, score: float, margin: float,
                 inat_species: str | None, inat_known: bool) -> tuple[str, str]:
    """Returns (label, status). `inat_known`: the second teacher has a label for `bioclip_species`."""
    if score >= AUTO_SCORE and margin >= AUTO_MARGIN and inat_species == bioclip_species:
        return bioclip_species, "auto"
    if not inat_known and score >= SINGLE_SCORE and margin >= SINGLE_MARGIN:
        return bioclip_species, "single"
    return UNIDENTIFIED, "review"


def _crop(frame: np.ndarray, box: Sequence[float]) -> np.ndarray:
    h, w = frame.shape[:2]
    x1 = min(max(math.floor(box[0]), 0), w - 1)
    y1 = min(max(math.floor(box[1]), 0), h - 1)
    x2 = min(max(math.ceil(box[2]), x1 + 1), w)
    y2 = min(max(math.ceil(box[3]), y1 + 1), h)
    return frame[y1:y2, x1:x2]


def label_frame(frame: np.ndarray, meta: dict,
                boxes_fn: Callable[[np.ndarray], list[tuple[Sequence[float], float]]],
                bioclip_fn: Callable[[list[np.ndarray]], list[tuple[str, float, float]]],
                inat_fn: Callable[[np.ndarray, str], tuple[str | None, float, bool]],
                species: Sequence[Species]) -> list[dict]:
    """Labels one BGR frame and returns its rows.

    `meta` has `split`, `video` and `frame` (path relative to the frames directory); the row ids
    are `<frame stem>#<box index>`, or `<frame stem>#-` when no bird is found.

    The teachers are plain functions so tests can stub them:
      boxes_fn(frame)                    -> [(box_xyxy, box_conf), ...]
      bioclip_fn(crops)                  -> [(species_key, score, margin), ...]  one per crop
      inat_fn(crop, bioclip_species)     -> (inat_species_key | None, prob, inat_known)
    `inat_known` says whether the iNaturalist label file has a label for `bioclip_species`, which
    is why that function also gets BioCLIP's answer. Species keys come from `species`; a key
    outside it raises ValueError.
    """
    stem = Path(meta["frame"]).stem
    where = {"split": meta["split"], "video": meta["video"], "frame": meta["frame"]}
    boxes = boxes_fn(frame)
    if not boxes:
        return [{"id": f"{stem}#-", **where, "box": None, "label": None, "status": "empty"}]

    crops = [_crop(frame, box) for box, _ in boxes]
    bioclip = bioclip_fn(crops)
    keys = {s.key for s in species}
    rows = []
    for i, ((box, box_conf), crop, (bio_species, score, margin)) in enumerate(zip(boxes, crops, bioclip)):
        if bio_species not in keys:
            raise ValueError(f"BioCLIP named {bio_species!r}, which is not in the species list")
        inat_species, inat_prob, inat_known = inat_fn(crop, bio_species)
        if inat_species is not None and inat_species not in keys:
            raise ValueError(f"iNaturalist named {inat_species!r}, which is not in the species list")
        label, status = decide_label(bio_species, score, margin, inat_species, inat_known)
        rows.append({
            "id": f"{stem}#{i}", **where,
            "box": [float(v) for v in box], "box_conf": float(box_conf),
            "bioclip": {"species": bio_species, "score": float(score), "margin": float(margin)},
            "inat": {"species": inat_species, "prob": float(inat_prob)},
            "label": label, "status": status})
    return rows


def _load_boxes_fn(model_name: str, imgsz: int, conf: float):
    from ultralytics import YOLO

    try:
        model = YOLO(model_name)
    except Exception as err:
        if model_name == FALLBACK_BOX_MODEL:
            raise
        print(f"cannot load {model_name} ({err}); using {FALLBACK_BOX_MODEL}", file=sys.stderr)
        model_name = FALLBACK_BOX_MODEL
        model = YOLO(model_name)

    def boxes_fn(frame):
        result = model.predict(frame, classes=[COCO_BIRD], imgsz=imgsz, conf=conf, verbose=False)[0]
        return list(zip(result.boxes.xyxy.cpu().numpy().tolist(), result.boxes.conf.cpu().numpy().tolist()))

    return boxes_fn, model_name


def _bioclip_results(preds: list[dict], n_crops: int, key_of: dict[str, str]) -> list[tuple[str, float, float]]:
    """(species_key, score, margin) per crop from pybioclip's flat prediction list.

    `CustomLabelsClassifier.predict` (pybioclip 2.1.6) returns one run of
    {"file_name": str(image index), "classification": label, "score": prob} per image, best first.
    """
    per_crop: list[list[float]] = [[] for _ in range(n_crops)]
    top: list[str | None] = [None] * n_crops
    for p in preds:
        i = int(p["file_name"])
        if not per_crop[i]:
            top[i] = key_of[p["classification"]]
        per_crop[i].append(float(p["score"]))
    if len(preds) == 0 or any(not scores for scores in per_crop):
        raise ValueError(f"BioCLIP returned predictions for {sum(bool(s) for s in per_crop)} of {n_crops} crops")
    return [(species, scores[0], scores[0] - scores[1] if len(scores) > 1 else scores[0])
            for species, scores in zip(top, per_crop)]


def _load_bioclip_fn(species: Sequence[Species]):
    import torch
    from bioclip import CustomLabelsClassifier
    from PIL import Image

    if torch.cuda.is_available():
        device = "cuda"
    else:
        device = "cpu"
        print("warning: no CUDA GPU found, BioCLIP runs on the CPU and labelling will be slow", file=sys.stderr)
    key_of = {f"{s.scientific} with common name {s.english}": s.key for s in species}
    classifier = CustomLabelsClassifier(list(key_of), model_str=BIOCLIP_MODEL, device=device)

    def bioclip_fn(crops):
        images = [Image.fromarray(np.ascontiguousarray(crop[:, :, ::-1])) for crop in crops]  # BGR to RGB
        preds = classifier.predict(images, k=len(key_of), batch_size=len(images), callback=lambda done, total: None)
        return _bioclip_results(preds, len(images), key_of)

    return bioclip_fn, f"{classifier.model_str} on {device}"


def _load_inat_fn(species: Sequence[Species]):
    from feeder_census.detectors.inat import InatClassifier

    classifier = InatClassifier(INAT_MODEL, INAT_LABELS)
    in_label_file = {line.split(" (")[0].strip() for line in INAT_LABELS.read_text().splitlines() if line.strip()}
    key_of = {name: s.key for s in species for name in (s.scientific, *s.aliases)}
    known = {s.key for s in species if in_label_file & {s.scientific, *s.aliases}}

    def inat_fn(crop, bioclip_species):
        name, prob = classifier.classify(crop)
        return key_of.get(name), prob, bioclip_species in known

    return inat_fn


def main(argv: list[str] | None = None) -> None:
    import cv2

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--frames", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--box-model", default="yolo26x.pt")
    ap.add_argument("--imgsz", type=int, default=1280)
    ap.add_argument("--box-conf", type=float, default=0.20)
    args = ap.parse_args(argv)

    species = load_species()
    boxes_fn, box_model = _load_boxes_fn(args.box_model, args.imgsz, args.box_conf)
    bioclip_fn, bioclip_info = _load_bioclip_fn(species)
    inat_fn = _load_inat_fn(species)
    print(f"teachers: boxes {box_model} (imgsz {args.imgsz}); BioCLIP {bioclip_info}; iNaturalist {INAT_MODEL.name}")

    frames = sorted(args.frames.rglob("*.jpg"))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    counts: Counter = Counter()
    with open(args.out, "w") as f:
        for n, path in enumerate(frames, 1):
            rel = path.relative_to(args.frames)
            frame = cv2.imread(str(path))
            if frame is None:
                print(f"warning: cannot read {path}", file=sys.stderr)
                continue
            meta = {"split": rel.parts[0], "video": rel.parts[1], "frame": rel.as_posix()}
            for row in label_frame(frame, meta, boxes_fn, bioclip_fn, inat_fn, species):
                f.write(json.dumps(row) + "\n")
                counts[(row["split"], row["label"] or "-", row["status"])] += 1
            if n % 100 == 0:
                print(f"{n}/{len(frames)} frames", flush=True)

    print(f"{'split':<8}{'label':<28}{'status':<10}boxes")
    for (split, label, status), n in sorted(counts.items()):
        print(f"{split:<8}{label:<28}{status:<10}{n}")


if __name__ == "__main__":
    main()
