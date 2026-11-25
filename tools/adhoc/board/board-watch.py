"""Watch the Arduino's demo through the tunnel: prints every change of latch state, pests, errors, and a summary."""
import json, sys, time, urllib.request
secs = int(sys.argv[1]) if len(sys.argv) > 1 else 180
last = None; changes = 0; fails = 0; ms = []; t0 = time.time(); closes = 0
while time.time() - t0 < secs:
    try:
        d = json.load(urllib.request.urlopen("http://localhost:8088/api/live", timeout=4))
        l = d["latch"]; state = (l["headline"], l["reason"], l["error"], d["pests"].get("red_squirrel"), d["error"])
        ms.append(d["detect_ms"])
        if state != last:
            changes += 1
            if l["headline"] == "closed" and (last is None or last[0] != "closed"): closes += 1
            print(time.strftime("%H:%M:%S"), "latch", l["headline"], "| reason", l["reason"], "| latch error", l["error"], "| squirrels in view", state[3], "| birds", {k: v for k, v in d["now"].items() if v}, "| error", d["error"], flush=True)
            last = state
    except Exception as e:
        fails += 1; print(time.strftime("%H:%M:%S"), "page not answering:", e, flush=True)
    time.sleep(1)
ms = [m for m in ms if m]
print(f"SUMMARY {secs} s: state changes {changes}, hatch closings {closes}, failed polls {fails}, detect_ms min {min(ms):.0f} median {sorted(ms)[len(ms)//2]:.0f} max {max(ms):.0f}" if ms else f"SUMMARY: no data, failed polls {fails}")
