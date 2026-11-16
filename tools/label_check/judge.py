"""Ad-hoc: ask the served vision-language model about every candidate crop.

    ~/vlm/bin/python data/judge.py <check dir> [--ports 8000,8001] [--workers 96] [--limit N]

Reads cands-*.jsonl and crops/, appends one line per candidate to verdicts.jsonl (resumable).
The model answers a closed question as JSON: what is in the centre, which species, is it sure.
"""
import base64, json, sys, time, threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from openai import OpenAI

root = Path(sys.argv[1])


def arg(name, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


ports = [int(p) for p in arg("--ports", "8000").split(",")]
workers = int(arg("--workers", "96"))
limit = int(arg("--limit", "0"))
clients = [OpenAI(base_url=f"http://127.0.0.1:{p}/v1", api_key="x", timeout=120, max_retries=2) for p in ports]
MODEL = clients[0].models.list().data[0].id

SPECIES = ["great_tit", "blue_tit", "bullfinch", "tree_sparrow", "house_sparrow", "magpie", "jay", "nuthatch",
           "great_spotted_woodpecker", "crested_tit", "coal_tit", "willow_tit", "other_bird", "cannot_tell", "none"]
SCHEMA = {
    "type": "object",
    "properties": {
        "what": {"type": "string", "enum": ["one_bird", "two_or_more_birds", "part_of_a_bird", "squirrel", "no_animal"]},
        "species": {"type": "string", "enum": SPECIES},
        "sure": {"type": "string", "enum": ["yes", "no"]},
    },
    "required": ["what", "species", "sure"],
    "additionalProperties": False,
}
PROMPT = """This picture is cut from a camera frame of a winter bird feeder in Finland. Look only at the thing in the CENTRE of the picture; ignore birds near the edges. Feeders (green wire mesh tubes, fat balls in a wire cage, a grey roofed feeder), branches, snow and overlaid text are not animals.

Answer three things:
1. what: "one_bird" if one whole or mostly visible bird is in the centre; "two_or_more_birds" if the centre holds two or more birds touching or overlapping; "part_of_a_bird" if only a small part of a bird is there (a tail, a wing tip, a cut-off body); "squirrel" for a squirrel; "no_animal" if there is no animal in the centre.
2. species of the central bird, one of:
- great_tit: black head with large white cheeks, yellow belly with a black stripe down the middle, greenish back. By far the most common bird here. Seen from behind or from the side its yellow belly can be hidden: a green back, blue-grey wings with one white bar and a black head with white cheeks is still a great tit.
- blue_tit: small; blue cap, white face with a dark line through the eye, yellow belly, blue wings.
- bullfinch: black cap, grey back, plump; male has a pink-red breast, female a grey-brown breast.
- tree_sparrow: chestnut-brown cap, white cheek with a black spot.
- house_sparrow: grey crown (male) or plain brown with a pale eyebrow (female), no cheek spot.
- magpie: large, black and white, very long tail.
- jay: large, pinkish-brown, blue patch on the wing, black moustache.
- nuthatch: blue-grey back, black line through the eye, pale underside, short tail, often head-down.
- great_spotted_woodpecker: black and white with red under the tail.
- crested_tit: pointed black-and-white crest. Rare here.
- coal_tit: black head, white cheeks, a white patch on the back of the neck, buff underside with no yellow and no green. Rare at this feeder.
- willow_tit: black cap, small black bib, pale grey-brown, no yellow and no green. Rare here.
- other_bird: clearly a bird, but none of these.
- cannot_tell: a bird, but the picture does not show enough to name it.
- none: not a bird.
3. sure: "yes" only if the marks you need are clearly visible; otherwise "no".

Reply with JSON only."""

cands = []
for f in sorted(root.glob("cands-*.jsonl")):
    cands += [json.loads(l) for l in f.read_text().splitlines()]
done = set()
vf = root / "verdicts.jsonl"
if vf.exists():
    done = {json.loads(l)["id"] for l in vf.read_text().splitlines() if l.strip()}
todo = [c for c in cands if c["id"] not in done]
if limit:
    todo = todo[:limit]
print("candidates", len(cands), "already judged", len(done), "to do", len(todo), "model", MODEL, flush=True)
lock = threading.Lock()
out = open(vf, "a")
t0 = time.time()
count = [0, 0]


def one(k_c):
    k, c = k_c
    try:
        b64 = base64.b64encode((root / "crops" / f"{c['id']}.jpg").read_bytes()).decode()
        r = clients[k % len(clients)].chat.completions.create(
            model=MODEL, temperature=0, max_tokens=60,
            messages=[{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                {"type": "text", "text": PROMPT}]}],
            response_format={"type": "json_schema", "json_schema": {"name": "verdict", "schema": SCHEMA, "strict": True}})
        v = json.loads(r.choices[0].message.content)
        row = dict(id=c["id"], **v)
    except Exception as exc:  # recorded, retried on the next run
        with lock:
            count[1] += 1
            if count[1] <= 3:
                print("error", type(exc).__name__, str(exc)[:200], flush=True)
        return
    with lock:
        out.write(json.dumps(row) + "\n")
        count[0] += 1
        if count[0] % 500 == 0:
            out.flush()
            print(f"{count[0]} judged, {count[0] / (time.time() - t0):.1f} per s, errors {count[1]}", flush=True)


with ThreadPoolExecutor(workers) as ex:
    list(ex.map(one, enumerate(todo)))
out.close()
print(f"done {count[0]} judged in {time.time() - t0:.0f} s ({count[0] / max(time.time() - t0, 1e-9):.1f} per s), errors {count[1]}", flush=True)
