"""Ad-hoc: score every labelled box for "is this a bird at all?" with a general CLIP model.

    python data/birdness.py <labels.jsonl> [frames dir]

Writes <labels>.birdness.json: {row id: probability that the crop is a bird}, plus two contact
sheets in data/check/ (lowest scores and the borderline band) so the cut-off can be checked by eye.
"""
import json
import random
import sys
from pathlib import Path

import cv2
import numpy as np
import open_clip
import torch
from PIL import Image

labels_path = Path(sys.argv[1])
frames_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("data/frames")
out = Path("data/check")
out.mkdir(exist_ok=True)
BIRD = ["a photo of a bird", "a small songbird perched at a bird feeder", "a bird seen from behind",
        "a blurry bird in flight", "a bird clinging to a wire feeder", "a large black and white bird"]
OTHER = ["a ball of suet in a wire cage", "fat balls in a bird feeder with no bird", "snow on a metal hook",
         "an empty bird feeder", "tree branches with no bird", "a wooden post", "a lump of snow"]

device = "cuda" if torch.cuda.is_available() else "cpu"
model, _, preprocess = open_clip.create_model_and_transforms("ViT-B-32", pretrained="laion2b_s34b_b79k")
model = model.to(device).eval()
tokenizer = open_clip.get_tokenizer("ViT-B-32")
with torch.no_grad():
    text = model.encode_text(tokenizer(BIRD + OTHER).to(device))
    text = text / text.norm(dim=-1, keepdim=True)

rows = [json.loads(line) for line in open(labels_path)]
boxes = [r for r in rows if r.get("status") != "empty"]
boxes.sort(key=lambda r: r["frame"])


def crop_of(frame, r):
    x1, y1, x2, y2 = [int(v) for v in r["box"]]
    pad = int(0.1 * max(x2 - x1, y2 - y1))
    return frame[max(0, y1 - pad):y2 + pad, max(0, x1 - pad):x2 + pad]


scores = {}
batch, ids = [], []


def flush():
    if not batch:
        return
    with torch.no_grad():
        image = model.encode_image(torch.stack(batch).to(device))
        image = image / image.norm(dim=-1, keepdim=True)
        probs = (100.0 * image @ text.T).softmax(dim=-1)
        bird = probs[:, :len(BIRD)].sum(dim=-1).tolist()
    scores.update(zip(ids, bird))
    batch.clear()
    ids.clear()


current, frame = None, None
for n, r in enumerate(boxes):
    if r["frame"] != current:
        current, frame = r["frame"], cv2.imread(str(frames_dir / r["frame"]))
    c = crop_of(frame, r)
    if c.size == 0:
        scores[r["id"]] = 0.0
        continue
    batch.append(preprocess(Image.fromarray(cv2.cvtColor(c, cv2.COLOR_BGR2RGB))))
    ids.append(r["id"])
    if len(batch) == 256:
        flush()
    if n % 2000 == 0:
        print(n, "/", len(boxes), flush=True)
flush()
Path(str(labels_path) + ".birdness.json").write_text(json.dumps(scores))

vals = sorted(scores.values())
print("boxes", len(vals), "quantiles", [round(vals[int(len(vals) * p)], 2) for p in (0.05, 0.1, 0.25, 0.5, 0.75)])
for lo, hi in ((0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.01)):
    print(f"birdness {lo}-{hi}: {sum(1 for v in vals if lo <= v < hi)}")


def sheet(name, items, n=48, cols=8, size=150):
    random.seed(11)
    items = random.sample(items, min(n, len(items)))
    tiles = []
    for r in items:
        c = crop_of(cv2.imread(str(frames_dir / r["frame"])), r)
        h, w = c.shape[:2]
        s = size / max(h, w)
        c = cv2.resize(c, (max(1, int(w * s)), max(1, int(h * s))))
        t = np.full((size, size, 3), 40, np.uint8)
        t[:c.shape[0], :c.shape[1]] = c
        cv2.putText(t, f"{scores[r['id']]:.2f} {r['bioclip']['species'][:5]} {r['bioclip']['score']:.2f}", (3, size - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 255, 255), 1)
        tiles.append(t)
    while len(tiles) % cols:
        tiles.append(np.full((size, size, 3), 40, np.uint8))
    cv2.imwrite(str(out / f"{name}.jpg"), np.vstack([np.hstack(tiles[i:i + cols]) for i in range(0, len(tiles), cols)]),
                [cv2.IMWRITE_JPEG_QUALITY, 82])


sheet("bn_low", [r for r in boxes if scores[r["id"]] < 0.3])
sheet("bn_mid", [r for r in boxes if 0.3 <= scores[r["id"]] < 0.7])
sheet("bn_high_unsure", [r for r in boxes if scores[r["id"]] >= 0.7 and r["bioclip"]["score"] < 0.6])
print("DONE")
