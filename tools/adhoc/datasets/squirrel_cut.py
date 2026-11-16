"""Ad-hoc: find the squirrel in every squirrel photo and in the squirrel video, and cut it out.

    python data/squirrel_cut.py

Inputs: data/squirrel_src/images/*.jpg (Creative Commons photos) and data/squirrel_src/orava-1h.mp4
(training only, never shown). Finds animals with two detectors, keeps the ones a CLIP model calls a squirrel, draws
the outline with SAM, and writes:
  data/frames/train/sqphoto/sqphoto_<n>.jpg       the photo, at most 1280 px wide (a training frame)
  data/frames/train/orava-1h/orava-1h_<ms>.jpg    video frames with a squirrel (training frames)
  data/squirrel_cut/<name>.png                    cut-outs with transparency, for pasting
  data/labels/squirrel_raw.jsonl                  label rows for the two kinds of training frames
  data/check/sq_cut_<k>.jpg                       contact sheets of the cut-outs, to check by eye
"""
import json
import subprocess
from pathlib import Path

import cv2
import numpy as np
import open_clip
import torch
from PIL import Image
from ultralytics import SAM, YOLO, YOLOWorld

root = Path("data")
cut_dir = root / "squirrel_cut"
cut_dir.mkdir(exist_ok=True)
(root / "check").mkdir(exist_ok=True)
NAMES = ["squirrel", "bird", "cat", "dog", "person", "marten", "rabbit", "animal"]
world = YOLOWorld("yolov8l-worldv2.pt")
world.set_classes(NAMES)
plain = YOLO("yolo26x.pt")
sam = SAM("sam2.1_b.pt")
device = "cuda" if torch.cuda.is_available() else "cpu"
clip, _, preprocess = open_clip.create_model_and_transforms("ViT-B-32", pretrained="laion2b_s34b_b79k")
clip = clip.to(device).eval()
SQ = ["a photo of a squirrel", "a red squirrel on a tree", "a squirrel eating", "a squirrel seen from behind"]
OTHER = ["a photo of a bird", "a photo of a dog", "a photo of a cat", "a tree trunk", "branches and leaves", "a person",
         "a bird feeder", "snow", "a hare", "a pine marten", "an owl", "a mouse", "text on a screen"]
with torch.no_grad():
    text = clip.encode_text(open_clip.get_tokenizer("ViT-B-32")(SQ + OTHER).to(device))
    text = text / text.norm(dim=-1, keepdim=True)
rows, cuts = [], []


def iou(a, b):
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    if w <= 0 or h <= 0:
        return 0.0
    inter = w * h
    return inter / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter)


def squirrels(image, conf):
    """Boxes that are a squirrel, best first: (x1, y1, x2, y2, squirrel score).

    The detectors often call a squirrel a dog, a cat or a bear, so any animal box from either
    detector is a candidate and a general CLIP model decides whether the crop shows a squirrel.
    """
    cand = []
    res = world.predict(image, conf=0.1, imgsz=960, verbose=False)[0]
    cand += [[float(v) for v in b.xyxy[0]] for b in res.boxes if NAMES[int(b.cls[0])] != "person"]
    res = plain.predict(image, conf=0.15, imgsz=960, verbose=False)[0]
    cand += [[float(v) for v in b.xyxy[0]] for b in res.boxes if res.names[int(b.cls[0])] != "person"]
    H, W = image.shape[:2]
    cand = [b for b in cand if min(b[2] - b[0], b[3] - b[1]) >= 40 and (b[2] - b[0]) * (b[3] - b[1]) < 0.9 * H * W]
    if not cand:
        return []
    crops = []
    for b in cand:
        x1, y1, x2, y2 = [int(v) for v in b]
        crops.append(preprocess(Image.fromarray(cv2.cvtColor(image[max(0, y1):y2, max(0, x1):x2], cv2.COLOR_BGR2RGB))))
    with torch.no_grad():
        emb = clip.encode_image(torch.stack(crops).to(device))
        emb = emb / emb.norm(dim=-1, keepdim=True)
        score = (100.0 * emb @ text.T).softmax(dim=-1)[:, :len(SQ)].sum(dim=-1).tolist()
    scored = sorted(((*b, s) for b, s in zip(cand, score) if s >= conf), key=lambda b: -b[4])
    kept = []
    for b in scored:
        if all(iou(b, k) < 0.5 for k in kept):
            kept.append(b)
    return kept


def cut_out(image, box, name):
    """Saves the animal inside `box` as a transparent PNG. Returns False when the outline is poor."""
    x1, y1, x2, y2 = [int(round(v)) for v in box[:4]]
    res = sam(image, bboxes=[[x1, y1, x2, y2]], verbose=False)[0]
    if res.masks is None or len(res.masks.data) == 0:
        return False
    mask = res.masks.data[0].cpu().numpy().astype(np.uint8)
    if mask.shape != image.shape[:2]:
        mask = cv2.resize(mask, (image.shape[1], image.shape[0]), interpolation=cv2.INTER_NEAREST)
    ys, xs = np.where(mask > 0)
    if len(xs) == 0:
        return False
    mx1, my1, mx2, my2 = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
    fill = mask[my1:my2, mx1:mx2].mean()
    if fill < 0.25 or (mx2 - mx1) < 60 or (my2 - my1) < 60:
        return False
    rgba = np.dstack([image[my1:my2, mx1:mx2], mask[my1:my2, mx1:mx2] * 255])
    cv2.imwrite(str(cut_dir / f"{name}.png"), rgba)
    cuts.append(name)
    return True


# 1. the photos
photo_dir = root / "frames" / "train" / "sqphoto"
photo_dir.mkdir(parents=True, exist_ok=True)
photos = sorted((root / "squirrel_src" / "images").glob("*.jpg"))
kept = 0
for n, path in enumerate(photos):
    image = cv2.imread(str(path))
    if image is None:
        continue
    h, w = image.shape[:2]
    if w > 1280:
        image = cv2.resize(image, (1280, round(h * 1280 / w)), interpolation=cv2.INTER_AREA)
        h, w = image.shape[:2]
    found = squirrels(image, 0.7)
    if not found:
        continue
    stem = f"sqphoto_{n:06d}"
    cv2.imwrite(str(photo_dir / f"{stem}.jpg"), image, [cv2.IMWRITE_JPEG_QUALITY, 90])
    for k, b in enumerate(found[:3]):
        rows.append({"id": f"{stem}#{k}", "split": "train", "video": "sqphoto", "frame": f"train/sqphoto/{stem}.jpg",
                     "box": [round(v, 1) for v in b[:4]], "box_conf": round(b[4], 3), "label": "red_squirrel",
                     "status": "auto", "source": path.name})
    best = found[0]
    if min(best[2] - best[0], best[3] - best[1]) >= 120 and best[4] >= 0.85:
        cut_out(image, best, f"photo_{n:06d}")
    kept += 1
print(f"photos {len(photos)}, with a squirrel {kept}, cut-outs {len(cuts)}", flush=True)

# 2. the video: one frame every 2 s
video = root / "squirrel_src" / "orava-1h.mp4"
tmp = root / "squirrel_src" / "orava_frames"
tmp.mkdir(exist_ok=True)
if not any(tmp.iterdir()):
    subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-i", str(video), "-vf", "fps=0.5", "-q:v", "3",
                    str(tmp / "f_%05d.jpg")], check=True)
video_dir = root / "frames" / "train" / "orava-1h"
video_dir.mkdir(parents=True, exist_ok=True)
frames = sorted(tmp.glob("f_*.jpg"))
n_video, n_cut_before = 0, len(cuts)
for i, path in enumerate(frames):
    image = cv2.imread(str(path))
    found = squirrels(image, 0.8)
    if not found:
        continue
    ms = (int(path.stem.split("_")[1]) - 1) * 2000
    stem = f"orava-1h_{ms:09d}"
    cv2.imwrite(str(video_dir / f"{stem}.jpg"), image, [cv2.IMWRITE_JPEG_QUALITY, 90])
    for k, b in enumerate(found[:3]):
        rows.append({"id": f"{stem}#{k}", "split": "train", "video": "orava-1h", "frame": f"train/orava-1h/{stem}.jpg",
                     "box": [round(v, 1) for v in b[:4]], "box_conf": round(b[4], 3), "label": "red_squirrel",
                     "status": "auto", "source": "orava-1h"})
    best = found[0]
    if n_video % 3 == 0 and min(best[2] - best[0], best[3] - best[1]) >= 120 and best[4] >= 0.9:
        cut_out(image, best, f"video_{ms:09d}")
    n_video += 1
    if i % 300 == 0:
        print(i, "/", len(frames), flush=True)
print(f"video frames {len(frames)}, with a squirrel {n_video}, cut-outs {len(cuts) - n_cut_before}", flush=True)

with open(root / "labels" / "squirrel_raw.jsonl", "w") as f:
    for r in rows:
        f.write(json.dumps(r) + "\n")

# 3. contact sheets of the cut-outs on a grey chequer
size, cols, per = 150, 10, 80
for page in range(0, len(cuts), per):
    tiles = []
    for name in cuts[page:page + per]:
        rgba = cv2.imread(str(cut_dir / f"{name}.png"), cv2.IMREAD_UNCHANGED)
        h, w = rgba.shape[:2]
        s = size / max(h, w)
        rgba = cv2.resize(rgba, (max(1, int(w * s)), max(1, int(h * s))))
        tile = np.full((size, size, 3), (200, 90, 200), np.uint8)
        a = rgba[:, :, 3:4] / 255.0
        tile[:rgba.shape[0], :rgba.shape[1]] = (rgba[:, :, :3] * a + tile[:rgba.shape[0], :rgba.shape[1]] * (1 - a)).astype(np.uint8)
        cv2.putText(tile, name[-9:], (3, size - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.36, (255, 255, 255), 1)
        tiles.append(tile)
    while len(tiles) % cols:
        tiles.append(np.full((size, size, 3), 40, np.uint8))
    cv2.imwrite(str(root / "check" / f"sq_cut_{page // per}.jpg"),
                np.vstack([np.hstack(tiles[i:i + cols]) for i in range(0, len(tiles), cols)]), [cv2.IMWRITE_JPEG_QUALITY, 82])
print("rows", len(rows), "cut-outs", len(cuts))
print("DONE")
