"""Ad-hoc: cut the busy parts of the held-out day (12 Nov) into a demo clip, from the scan results.

Uses data/frames/mining.csv (one row per scanned second). A second counts as busy when the scan
model saw at least one bird with confidence >= 0.45. Busy seconds closer than 3 s are merged,
each segment is padded by 2 s, segments shorter than 5 s are skipped, and the segments with the
most busy seconds are kept until the clip is about 10 minutes. Writes
data/highlights/feeder-12nov-highlights.mp4 and the same name + .segments.csv.
"""
import csv
import subprocess
from pathlib import Path

VIDEO = "talvilintulive-20261112"
src = Path("data/videos/train") / f"{VIDEO}.mp4"
out_dir = Path("data/highlights")
out_dir.mkdir(exist_ok=True)
work = out_dir / "parts12"
work.mkdir(exist_ok=True)
MAX_TOTAL, PAD, GAP, MIN_LEN = 600.0, 2.0, 3.0, 5.0

rows = [r for r in csv.DictReader(open("data/frames/mining.csv")) if r["video"] == VIDEO]
busy = sorted((int(r["ms"]) / 1000.0, int(r["n_boxes"])) for r in rows
              if int(r["n_boxes"]) >= 1 and float(r["max_conf"]) >= 0.45)
length = max(int(r["ms"]) for r in rows) / 1000.0
segs = []
for t, n in busy:
    if segs and t - segs[-1][1] <= GAP:
        segs[-1][1] = t
        segs[-1][2] = max(segs[-1][2], n)
        segs[-1][3] += 1
    else:
        segs.append([t, t, n, 1])
segs = [[max(0.0, a - PAD), min(length, b + PAD), peak, count] for a, b, peak, count in segs]
segs = [s for s in segs if s[1] - s[0] >= MIN_LEN]
chosen, total = [], 0.0
for s in sorted(segs, key=lambda s: (-s[2], -s[3])):
    d = s[1] - s[0]
    if total + d > MAX_TOTAL:
        continue
    chosen.append(s)
    total += d
chosen.sort()
print(f"busy seconds {len(busy)}, segments {len(segs)}, chosen {len(chosen)}, total {total:.0f} s")

parts = []
for i, (a, b, peak, count) in enumerate(chosen):
    part = work / f"p{i:03d}.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-ss", f"{a:.3f}", "-i", str(src), "-t", f"{b - a:.3f}",
                    "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "22", "-pix_fmt", "yuv420p", "-r", "30",
                    str(part)], check=True)
    parts.append(part)
(work / "list.txt").write_text("".join(f"file '{p.name}'\n" for p in parts))
clip = out_dir / "feeder-12nov-highlights.mp4"
subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-f", "concat", "-safe", "0", "-i", str(work / "list.txt"),
                "-c", "copy", "-movflags", "+faststart", str(clip)], check=True)
with open(str(clip) + ".segments.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["start_s", "end_s", "peak_boxes"])
    for a, b, peak, count in chosen:
        w.writerow([f"{a:.1f}", f"{b:.1f}", peak])
print("DONE", clip, clip.stat().st_size // 1_000_000, "MB")
