"""Ad-hoc: third labelling pass (ruling R32). A classifier trained on this camera's own clear cases
decides bird or not; a squirrel score finds the real squirrel visits.

    python data/relabel3.py <tag> <labels.jsonl> [<labels.jsonl> ...]

Each labels file needs <file>.emb.npz from embed.py. Writes data/labels/<tag>.jsonl (all inputs
joined; split: 12 Nov = held-out `demo`, the rest `train`; squirrel boxes relabelled `red_squirrel`
in place), data/review/corrections_<tag>.csv and contact sheets data/check/r3_*.jpg.

Rule per box, first match wins:
  squirrel classifier >= 0.6 (feeder camera only)           -> red_squirrel
  both teachers agreed (status auto)                        -> keep their species
  BioCLIP score >= 0.9 and margin >= 0.6                    -> BioCLIP species
  not a bird (classifier < 0.85 on the feeder camera,
              zero-shot bird score < 0.5 on other footage)  -> drop
  this camera's species classifier >= 0.85                  -> that species (other footage: BioCLIP >= 0.8, margin >= 0.5)
  otherwise                                                 -> unidentified (a bird we cannot name)
`catv-` videos are not from Finland: willow tit there becomes unidentified.
"""
import collections
import csv
import json
import random
import sys
from pathlib import Path

import cv2
import numpy as np
import torch

root = Path("data")
tag = sys.argv[1]
held_out = "talvilintulive-20261112"
rows, emb, zs_bird, zs_sq = [], {}, {}, {}
for name in sys.argv[2:]:
    rows += [json.loads(line) for line in open(name)]
    z = np.load(name + ".emb.npz")
    for i, e, b, s in zip(z["ids"], z["emb"], z["bird"], z["sq"]):
        emb[str(i)], zs_bird[str(i)], zs_sq[str(i)] = e.astype(np.float32), float(b), float(s)
# kept out of everything: the squirrel's first visit on 22 Oct, shown in the demo as footage the model never saw
HOLD_OUT = [("talvilintulive-20261022", 3_990_000, 4_250_000)]


def held(r):
    ms = int(Path(r["frame"]).stem.rsplit("_", 1)[1])
    return any(r["video"] == v and a <= ms <= b for v, a, b in HOLD_OUT)


n_before = len(rows)
rows = [r for r in rows if not held(r)]
print(f"held out for the demo: {n_before - len(rows)} rows")
seen = set()
for r in rows:
    assert r["id"] not in seen, f"duplicate id {r['id']}"
    seen.add(r["id"])
    r["split"] = "demo" if r["video"] == held_out else "train"
boxes = [r for r in rows if r.get("status") != "empty" and r["id"] in emb]

# squirrel score from clean prompts: best squirrel prompt against best bird prompt and best "thing" prompt
import open_clip  # noqa: E402
SQ = ["a photo of a squirrel", "a red squirrel", "a squirrel with a bushy tail", "a squirrel climbing a wooden pole"]
BIRDS = ["a photo of a bird", "a small songbird", "a great tit", "a blue tit", "a sparrow", "a jay", "a bullfinch", "a magpie",
         "a woodpecker", "a bird at a bird feeder", "a blurry bird in flight"]
THINGS = ["a ball of suet in a wire cage", "fat balls in a bird feeder", "snow on a metal hook", "an empty bird feeder",
          "tree branches", "a wooden post"]
clip_model, _, _ = open_clip.create_model_and_transforms("ViT-B-32", pretrained="laion2b_s34b_b79k")
with torch.no_grad():
    T = clip_model.encode_text(open_clip.get_tokenizer("ViT-B-32")(SQ + BIRDS + THINGS))
    T = (T / T.norm(dim=-1, keepdim=True)).numpy()
E = np.stack([emb[r["id"]] for r in boxes])
L = 100.0 * E @ T.T
three = np.stack([L[:, :len(SQ)].max(1), L[:, len(SQ):len(SQ) + len(BIRDS)].max(1), L[:, len(SQ) + len(BIRDS):].max(1)], axis=1)
three = np.exp(three - three.max(1, keepdims=True))
zs_sq = {r["id"]: float(v) for r, v in zip(boxes, three[:, 0] / three.sum(1))}
feeder = [r for r in boxes if r["video"].startswith("talvilintulive-")]

# the bird-or-not classifier: clear birds against clear non-birds, both from the feeder camera
pos = [r for r in feeder if r.get("source") != "big" and zs_sq[r["id"]] < 0.5 and (r["status"] == "auto" or (
    r["bioclip"]["score"] >= 0.9 and r["bioclip"]["margin"] >= 0.6 and zs_bird[r["id"]] >= 0.5))]
neg = [r for r in feeder if r.get("source") != "big" and zs_sq[r["id"]] < 0.5 and r["status"] != "auto" and zs_bird[r["id"]] < 0.1
       and r["bioclip"]["score"] < 0.5]
random.seed(5)
random.shuffle(pos)
random.shuffle(neg)
hold_p, hold_n = pos[:len(pos) // 10], neg[:len(neg) // 10]
train_p, train_n = pos[len(pos) // 10:], neg[len(neg) // 10:]
def fit(positives, negatives):
    """Logistic regression on the embeddings, classes weighted equally. Returns a scoring function for a row."""
    X = torch.tensor(np.stack([emb[r["id"]] for r in positives + negatives]))
    y = torch.tensor([1.0] * len(positives) + [0.0] * len(negatives))
    weight = torch.where(y > 0.5, len(y) / (2.0 * len(positives)), len(y) / (2.0 * len(negatives)))
    w = torch.zeros(X.shape[1], requires_grad=True)
    b = torch.zeros(1, requires_grad=True)
    opt = torch.optim.LBFGS([w, b], max_iter=300, line_search_fn="strong_wolfe")

    def closure():
        opt.zero_grad()
        loss = torch.nn.functional.binary_cross_entropy_with_logits(X @ w * 20 + b, y, weight=weight) + 1e-3 * (w * w).sum()
        loss.backward()
        return loss

    opt.step(closure)
    w_np, b_np = w.detach().numpy(), float(b.detach())
    return lambda r: float(1 / (1 + np.exp(-(emb[r["id"]] @ w_np * 20 + b_np))))


p_bird = fit(train_p, train_n)
sq_seeds = [r for r in feeder if r.get("source") != "big" and zs_sq[r["id"]] >= 0.9 and r["status"] != "auto" and r["bioclip"]["score"] < 0.7]
p_sq = fit(sq_seeds, train_p[:3000] + train_n) if len(sq_seeds) >= 10 else (lambda r: 0.0)
print(f"squirrel seeds: {len(sq_seeds)}")
# second round: reseed from the near-certain cases only, against everything the first round was sure is not a squirrel
q1 = {r["id"]: p_sq(r) for r in feeder if r["status"] != "auto"}
seeds2 = [r for r in feeder if q1.get(r["id"], 0.0) >= 0.999]
rest = [r for r in feeder if q1.get(r["id"], 0.0) < 0.3]
random.shuffle(rest)
if len(seeds2) >= 10:
    p_sq = fit(seeds2, rest[:8000])
print(f"squirrel seeds, second round: {len(seeds2)}")
ok_p = sum(p_bird(r) >= 0.5 for r in hold_p)
ok_n = sum(p_bird(r) < 0.5 for r in hold_n)
print(f"classifier seeds: {len(pos)} birds, {len(neg)} non-birds; held-back check: birds {ok_p}/{len(hold_p)}, "
      f"non-birds {ok_n}/{len(hold_n)}")

# species classifier: this camera's clear cases (both teachers agreed, or BioCLIP near certain) teach a
# per-species classifier on the same embeddings; it then names the boxes BioCLIP was unsure about
def seed_species(r):
    return r["label"] if r["status"] == "auto" else r["bioclip"]["species"]


sp_count = collections.Counter(seed_species(r) for r in pos)
sp_classes = sorted(k for k, n in sp_count.items() if n >= 40)
sp_index = {k: i for i, k in enumerate(sp_classes)}
sp_seeds = [r for r in pos if seed_species(r) in sp_index]
sp_hold, sp_train = sp_seeds[:len(sp_seeds) // 10], sp_seeds[len(sp_seeds) // 10:]
Xs = torch.tensor(np.stack([emb[r["id"]] for r in sp_train]))
ys = torch.tensor([sp_index[seed_species(r)] for r in sp_train])
cw = torch.tensor([min(8.0, len(sp_train) / (len(sp_classes) * max(1, int((ys == i).sum())))) for i in range(len(sp_classes))])
Ws = torch.zeros(Xs.shape[1], len(sp_classes), requires_grad=True)
bs = torch.zeros(len(sp_classes), requires_grad=True)
opt_s = torch.optim.LBFGS([Ws, bs], max_iter=400, line_search_fn="strong_wolfe")


def closure_s():
    opt_s.zero_grad()
    loss = torch.nn.functional.cross_entropy(Xs @ Ws * 20 + bs, ys, weight=cw) + 1e-3 * (Ws * Ws).sum()
    loss.backward()
    return loss


opt_s.step(closure_s)
Ws_np, bs_np = Ws.detach().numpy(), bs.detach().numpy()


def species_of(r):
    z = emb[r["id"]] @ Ws_np * 20 + bs_np
    z = np.exp(z - z.max())
    z = z / z.sum()
    return sp_classes[int(z.argmax())], float(z.max())


right = collections.Counter()
total = collections.Counter()
for r in sp_hold:
    total[seed_species(r)] += 1
    right[seed_species(r)] += species_of(r)[0] == seed_species(r)
print(f"species classifier: classes {sp_classes}; held-back accuracy {sum(right.values())}/{sum(total.values())}; per species "
      + ", ".join(f"{k} {right[k]}/{total[k]}" for k in sp_classes))
SP_CUT = 0.85
SQ_SURE = 0.985  # real squirrels score 0.99 and up; sticks and blurred birds sit between 0.6 and 0.98
BIRD_CUT = 0.85  # sticks and fat balls sit between 0.5 and 0.85; clear birds score 0.99 and up

corrections, groups = {}, collections.defaultdict(list)
for r in boxes:
    score, margin = (r["bioclip"]["score"], r["bioclip"]["margin"]) if r.get("bioclip") else (0.0, 0.0)
    on_feeder = r["video"].startswith("talvilintulive-")
    bird = p_bird(r) if on_feeder else zs_bird[r["id"]]
    r["_p"] = bird
    r["_q"] = p_sq(r) if on_feeder and r["status"] != "auto" else 0.0
    big_sq = r.get("big_class") == "red_squirrel"  # the in-domain teacher proposed a squirrel here
    if r["_q"] >= SQ_SURE or (big_sq and r["box_conf"] >= 0.6 and r["_q"] >= 0.6):
        r["label"], r["status"] = "red_squirrel", "auto"
        groups["squirrel_from_teacher" if r["_q"] < SQ_SURE else "squirrel"].append(r)
        continue
    if big_sq or r["_q"] >= 0.6:  # maybe a squirrel, maybe a stick or a blurred bird: teach it as neither
        corrections[r["id"]] = "drop"
        groups["squirrel_proposal_dropped" if big_sq else "squirrel_unsure_dropped"].append(r)
        continue
    if 0.1 <= r["_q"] < 0.6:
        groups["squirrel_maybe"].append(r)
    if on_feeder and bird < 0.5:
        # a confident name on a box the bird-or-not classifier rejects is a box round the whole feeder, or a fat ball
        new = "drop"
        groups["agreed_but_not_bird" if r["status"] == "auto" else
               "sure_name_but_not_bird" if score >= 0.9 and margin >= 0.6 else "dropped"].append(r)
    elif r["status"] == "auto":
        new = r["label"]
    elif score >= 0.9 and margin >= 0.6:
        new = r["bioclip"]["species"]
    elif bird < (BIRD_CUT if on_feeder else 0.5):
        new = "drop"
        groups["dropped_close" if bird >= 0.5 else "dropped"].append(r)
    elif on_feeder and species_of(r)[1] >= SP_CUT:
        new = species_of(r)[0]
        groups["named_by_classifier_agrees" if new == r["bioclip"]["species"] else "named_by_classifier_differs"].append(r)
    elif not on_feeder and score >= 0.8 and margin >= 0.5:
        new = r["bioclip"]["species"]
        groups["named_mid"].append(r)
    else:
        new = "unidentified"
        groups["unidentified"].append(r)
    if r["video"].startswith("catv-") and new == "willow_tit":
        new = "unidentified"
    if new != r["label"]:
        corrections[r["id"]] = new

with open(root / "labels" / f"{tag}.jsonl", "w") as f:
    for r in rows:
        f.write(json.dumps({k: v for k, v in r.items() if k not in ("_p", "_q")}) + "\n")
with open(root / "review" / f"corrections_{tag}.csv", "w", newline="") as f:
    out = csv.writer(f)
    out.writerow(["id", "label"])
    out.writerows(sorted(corrections.items()))

final = collections.defaultdict(collections.Counter)
for r in rows:
    if r.get("status") == "empty":
        final[r["split"]]["(empty frame)"] += 1
    elif r["id"] in emb:
        final[r["split"]][corrections.get(r["id"], r["label"])] += 1
for split in ("train", "demo"):
    print(split, sum(final[split].values()), sorted(final[split].items(), key=lambda kv: -kv[1]))
print("groups:", {k: len(v) for k, v in groups.items()})
sq_by_video = collections.Counter(r["video"] for r in groups["squirrel"])
print("squirrel boxes by video:", dict(sq_by_video))
sq_frames = sorted({r["frame"] for r in groups["squirrel"]})
print("squirrel frames:", len(sq_frames), sq_frames[:3], sq_frames[-3:])


def sheet(name, items, n=64, cols=8, size=150):
    random.seed(11)
    items = sorted(random.sample(items, min(n, len(items))), key=lambda r: r["frame"])
    tiles, cache = [], {}
    for r in items:
        if r["frame"] not in cache:
            cache = {r["frame"]: cv2.imread(str(root / "frames" / r["frame"]))}
        x1, y1, x2, y2 = [int(v) for v in r["box"]]
        pad = int(0.1 * max(x2 - x1, y2 - y1))
        c = cache[r["frame"]][max(0, y1 - pad):y2 + pad, max(0, x1 - pad):x2 + pad]
        h, wd = c.shape[:2]
        s = size / max(h, wd)
        c = cv2.resize(c, (max(1, int(wd * s)), max(1, int(h * s))))
        t = np.full((size, size, 3), 40, np.uint8)
        t[:c.shape[0], :c.shape[1]] = c
        sp = r["bioclip"]["species"][:5] if r.get("bioclip") else ""
        sc = r["bioclip"]["score"] if r.get("bioclip") else 0
        cv2.putText(t, f"{r['_p']:.2f} {sp} {sc:.2f} q{r['_q']:.2f}", (3, size - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.36,
                    (0, 255, 255), 1)
        cv2.putText(t, "-> " + str(corrections.get(r["id"], r["label"]))[:12], (3, 12), cv2.FONT_HERSHEY_SIMPLEX, 0.4,
                    (0, 255, 0), 1)
        tiles.append(t)
    if not tiles:
        return
    while len(tiles) % cols:
        tiles.append(np.full((size, size, 3), 40, np.uint8))
    cv2.imwrite(str(root / "check" / f"r3_{name}.jpg"),
                np.vstack([np.hstack(tiles[i:i + cols]) for i in range(0, len(tiles), cols)]), [cv2.IMWRITE_JPEG_QUALITY, 82])


for name, items in groups.items():
    sheet(name, items)
other = [r for r in boxes if not r["video"].startswith("talvilintulive-")]
sheet("other_footage_kept", [r for r in other if corrections.get(r["id"], r["label"]) != "drop"])
sheet("other_footage_dropped", [r for r in other if corrections.get(r["id"], r["label"]) == "drop"])
old_cam = [r for r in boxes if r["video"].startswith("talvilintulive-202") and not r["video"].startswith("talvilintulive-2026")]
sheet("older_years_kept", [r for r in old_cam if corrections.get(r["id"], r["label"]) != "drop"])
sheet("older_years_dropped", [r for r in old_cam if corrections.get(r["id"], r["label"]) == "drop"])
per_video = collections.Counter((r["video"], corrections.get(r["id"], r["label"]) == "red_squirrel" or r["label"] == "red_squirrel") for r in boxes)
print("boxes per video:", {v: n for (v, sq), n in sorted(per_video.items()) if not sq})
print("DONE")
