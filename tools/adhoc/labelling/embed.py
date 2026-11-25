"""Ad-hoc: CLIP embedding and two zero-shot scores for every labelled box.

    python data/embed.py <labels.jsonl> [frames dir]

Writes <labels>.emb.npz with `ids`, `emb` (unit vectors, float16), `bird` (bird against fat ball,
snow, empty feeder) and `sq` (squirrel against everything else). relabel3.py reads it.
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import open_clip
import torch
from PIL import Image

labels_path = Path(sys.argv[1])
frames_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("data/frames")
BIRD = ["a photo of a bird", "a small songbird perched at a bird feeder", "a bird seen from behind",
        "a blurry bird in flight", "a bird clinging to a wire feeder", "a large black and white bird"]
OTHER = ["a ball of suet in a wire cage", "fat balls in a bird feeder with no bird", "snow on a metal hook",
         "an empty bird feeder", "tree branches with no bird", "a wooden post", "a lump of snow"]
SQ = ["a photo of a squirrel", "a red squirrel climbing", "a squirrel eating at a bird feeder", "a squirrel seen from behind"]

device = "cuda" if torch.cuda.is_available() else "cpu"
model, _, preprocess = open_clip.create_model_and_transforms("ViT-B-32", pretrained="laion2b_s34b_b79k")
model = model.to(device).eval()
with torch.no_grad():
    text = model.encode_text(open_clip.get_tokenizer("ViT-B-32")(BIRD + OTHER + SQ).to(device))
    text = text / text.norm(dim=-1, keepdim=True)
nb, no = len(BIRD), len(OTHER)

rows = [json.loads(line) for line in open(labels_path)]
boxes = sorted((r for r in rows if r.get("status") != "empty"), key=lambda r: r["frame"])
ids, embs, bird, sq = [], [], [], []
batch, batch_ids = [], []


def flush():
    if not batch:
        return
    with torch.no_grad():
        e = model.encode_image(torch.stack(batch).to(device))
        e = e / e.norm(dim=-1, keepdim=True)
        logits = 100.0 * e @ text.T
        bird.extend(logits[:, :nb + no].softmax(dim=-1)[:, :nb].sum(dim=-1).tolist())
        sq.extend(logits.softmax(dim=-1)[:, nb + no:].sum(dim=-1).tolist())
    embs.append(e.cpu().numpy().astype(np.float16))
    ids.extend(batch_ids)
    batch.clear()
    batch_ids.clear()


current, frame = None, None
for n, r in enumerate(boxes):
    if r["frame"] != current:
        current, frame = r["frame"], cv2.imread(str(frames_dir / r["frame"]))
    x1, y1, x2, y2 = [int(v) for v in r["box"]]
    pad = int(0.1 * max(x2 - x1, y2 - y1))
    c = frame[max(0, y1 - pad):y2 + pad, max(0, x1 - pad):x2 + pad]
    if c.size == 0:
        continue
    batch.append(preprocess(Image.fromarray(cv2.cvtColor(c, cv2.COLOR_BGR2RGB))))
    batch_ids.append(r["id"])
    if len(batch) == 256:
        flush()
    if n % 2000 == 0:
        print(n, "/", len(boxes), flush=True)
flush()
np.savez(str(labels_path) + ".emb.npz", ids=np.array(ids), emb=np.concatenate(embs), bird=np.array(bird, np.float32),
         sq=np.array(sq, np.float32))
sq_a = np.array(sq)
print("boxes", len(ids), "squirrel score >=0.5:", int((sq_a >= 0.5).sum()), ">=0.8:", int((sq_a >= 0.8).sum()))
by_video = {}
for i, s in zip(ids, sq):
    if s >= 0.8:
        by_video[i.rsplit("_", 1)[0]] = by_video.get(i.rsplit("_", 1)[0], 0) + 1
print("squirrel boxes by video:", by_video)
print("DONE")
