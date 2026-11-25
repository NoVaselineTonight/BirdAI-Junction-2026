"""Ad-hoc: population-based training of the feeder student on one machine.

    python data/evolve.py --root data/evo/run1 --start W.pt --gpus 0,1,2,3 --per-gpu 2 --generations 20

Every generation each member trains one epoch from its own weights with its own settings and is scored on
checked validation footage (data/evo_one.py). The top quarter stays as it is; every other member is replaced by a
copy of a random top member's weights with mutated settings. Member 0 of generation 0 uses the plain settings, so
the run always contains the unchanged recipe. State is on disk: rerunning continues after the last full generation.
"""
import argparse, json, math, random, subprocess, sys, time
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--root", required=True)
ap.add_argument("--start", required=True)
ap.add_argument("--gpus", default="0")
ap.add_argument("--per-gpu", type=int, default=1)
ap.add_argument("--generations", type=int, default=10)
ap.add_argument("--epochs", type=int, default=1)
ap.add_argument("--workers", type=int, default=12)
ap.add_argument("--seed", type=int, default=0)
ap.add_argument("--python", default=".venv/bin/python")
ap.add_argument("--fit-dataset", default="")
ap.add_argument("--fit-split", default="val")
ap.add_argument("--val-every", type=int, default=3)
a = ap.parse_args()
root = Path(a.root); root.mkdir(parents=True, exist_ok=True)
gpus = [g for g in a.gpus.split(",") if g != ""]
N = len(gpus) * a.per_gpu
rng = random.Random(a.seed)

# gene: (low, high, log scale?, plain value)
GENES = {
    "lr0": (2e-5, 2e-3, True, 5.5e-4), "lrf": (0.01, 1.0, True, 0.01), "weight_decay": (1e-5, 2e-3, True, 5e-4),
    "warmup_epochs": (0.0, 0.5, False, 0.1), "box": (4.0, 11.0, False, 7.5), "cls": (0.25, 1.2, False, 0.5),
    "dfl": (0.8, 2.5, False, 1.5), "hsv_h": (0.0, 0.04, False, 0.015), "hsv_s": (0.2, 0.9, False, 0.7),
    "hsv_v": (0.1, 0.7, False, 0.4), "degrees": (0.0, 10.0, False, 0.0), "translate": (0.0, 0.25, False, 0.1),
    "scale": (0.1, 0.9, False, 0.5), "fliplr": (0.0, 0.5, False, 0.5), "mosaic": (0.0, 1.0, False, 1.0),
    "mixup": (0.0, 0.3, False, 0.0), "erasing": (0.0, 0.5, False, 0.4),
}
PLAIN = {k: v[3] for k, v in GENES.items()}


def clip(k, v):
    lo, hi = GENES[k][0], GENES[k][1]
    return float(min(max(v, lo), hi))


def mutate(h, strength=1.0):
    out = dict(h)
    for k, (lo, hi, log, _) in GENES.items():
        r = rng.random()
        if r < 0.10:  # fresh draw
            out[k] = math.exp(rng.uniform(math.log(lo), math.log(hi))) if log else rng.uniform(lo, hi)
        elif r < 0.60:  # nudge
            if log:
                out[k] = clip(k, h[k] * math.exp(rng.gauss(0, 0.35 * strength)))
            else:
                out[k] = clip(k, h[k] + rng.gauss(0, 0.15 * strength) * (hi - lo))
        out[k] = round(out[k], 6)
    return out


def log(msg):
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    with open(root / "evo.log", "a") as fh:
        fh.write(line + "\n")


state_file = root / "state.json"
if state_file.exists():
    state = json.loads(state_file.read_text())
    log(f"resuming after generation {state['gen'] - 1}")
else:
    GENTLE = dict(PLAIN, lr0=5e-5, mosaic=0.0, mixup=0.0, scale=0.2, translate=0.05, hsv_s=0.4, hsv_v=0.2, erasing=0.0)
    members = [dict(weights=a.start, hyp=PLAIN, origin="start (untrained)", frozen=True),
               dict(weights=a.start, hyp=PLAIN, origin="plain"), dict(weights=a.start, hyp=GENTLE, origin="gentle")]
    members += [dict(weights=a.start, hyp=mutate(rng.choice([PLAIN, GENTLE]), 1.5), origin="mutant") for _ in range(N - 3)]
    state = dict(gen=0, members=members, best=None, history=[])

while state["gen"] < a.generations:
    g = state["gen"]
    procs = []
    for i, m in enumerate(state["members"]):
        out = root / f"g{g:02d}" / f"m{i:02d}"
        if m.get("frozen") and m.get("result"):
            procs.append((i, out, None))
            continue
        cmd = [a.python, "data/evo_one.py"] + (["--score-only"] if m.get("frozen") else []) + ["--parent", m["weights"], "--hyp", json.dumps(m["hyp"]), "--out", str(out),
               "--epochs", str(a.epochs), "--workers", str(a.workers), "--fit-split", a.fit_split, "--val-every", str(a.val_every)] + (["--fit-dataset", a.fit_dataset] if a.fit_dataset else [])
        env = dict(__import__("os").environ, CUDA_VISIBLE_DEVICES=gpus[i % len(gpus)], PYTHONPATH=".:tools", OMP_NUM_THREADS="4")
        out.mkdir(parents=True, exist_ok=True)
        procs.append((i, out, subprocess.Popen(cmd, env=env, stdout=open(out / "log.txt", "w"), stderr=subprocess.STDOUT)))
    results = []
    for i, out, p in procs:
        if p is None:
            results.append(dict(state["members"][i]["result"], i=i, origin=state["members"][i]["origin"]))
            continue
        p.wait()
        rf = out / "result.json"
        if p.returncode == 0 and rf.exists():
            r = json.loads(rf.read_text())
            results.append(dict(i=i, fitness=r["fitness"], thr=r["thr"], P=r["P"], R=r["R"], exact50=r["exact50"],
                                weights=r["weights"], hyp=state["members"][i]["hyp"], origin=state["members"][i]["origin"]))
        else:
            log(f"gen {g} member {i} failed (exit {p.returncode}); see {out / 'log.txt'}")
    if not results:
        log("every member failed; stopping"); sys.exit(1)
    results.sort(key=lambda r: (-r["fitness"], -r["R"]))
    top = results[: max(1, len(results) // 4)]
    if state["best"] is None or results[0]["fitness"] > state["best"]["fitness"]:
        state["best"] = dict(results[0], gen=g)
    fits = [r["fitness"] for r in results]
    log(f"gen {g}: best {fits[0]:.4f} (thr {results[0]['thr']}, P {results[0]['P']:.3f}, R {results[0]['R']:.3f}, {results[0]['origin']} m{results[0]['i']}) "
        f"median {sorted(fits)[len(fits) // 2]:.4f} worst {fits[-1]:.4f} | best ever {state['best']['fitness']:.4f} (gen {state['best']['gen']})")
    state["history"].append(dict(gen=g, results=[{k: r[k] for k in ("i", "fitness", "thr", "P", "R", "exact50", "origin")} for r in results]))
    members = []
    for k in range(N):
        if k == 0:  # the best member is carried over untouched, so a generation can never lose it
            e = results[0]
            members.append(dict(weights=e["weights"], hyp=e["hyp"], origin=e["origin"] if e["origin"].startswith("elite") or "untrained" in e["origin"] else f"elite from g{g}m{e['i']}",
                                frozen=True, result={k2: e[k2] for k2 in ("fitness", "thr", "P", "R", "exact50", "weights", "hyp")}))
        elif k < len(top):
            members.append(dict(weights=top[k]["weights"], hyp=top[k]["hyp"], origin=f"kept g{g}m{top[k]['i']}"))
        else:
            parent = rng.choice(top)
            members.append(dict(weights=parent["weights"], hyp=mutate(parent["hyp"]), origin=f"child of g{g}m{parent['i']}"))
    state["members"] = members
    state["gen"] = g + 1
    state_file.write_text(json.dumps(state))
log(f"finished: best fitness {state['best']['fitness']:.4f} at cut-off {state['best']['thr']} from generation {state['best']['gen']}, weights {state['best']['weights']}")
(root / "best.json").write_text(json.dumps(state["best"]))
