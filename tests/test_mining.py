import csv
import os
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

import mine_frames
from mine_frames import highlight_segments, select_frames

ROOT = Path(__file__).resolve().parent.parent


def _by_ms(decisions):
    return {d.ms: d for d in decisions}


def _kept(decisions, *reasons):
    return [d.ms for d in decisions if d.kept and (not reasons or d.reason in reasons)]


def _bird_run(n=60, boxes=1, conf=0.9, step=1000, start=0):
    return [(start + i * step, boxes, conf) for i in range(n)]


# select_frames ---------------------------------------------------------------------------------

def test_a_bird_sitting_still_keeps_about_one_frame_in_four():
    decisions = select_frames(_bird_run(60), min_gap_s=4.0, empty_share=0.0, max_frames=1000)
    kept = _kept(decisions)
    assert 14 <= len(kept) <= 16
    assert all(b - a >= 4000 for a, b in zip(kept, kept[1:]))
    assert {d.reason for d in decisions if d.kept} == {"bird"}
    assert {d.reason for d in decisions if not d.kept} == {"skipped-duplicate"}


def test_a_change_in_the_number_of_birds_is_kept_at_once():
    samples = [(i * 1000, 1 if i < 5 else 2, 0.9) for i in range(10)]
    by_ms = _by_ms(select_frames(samples, 4.0, 0.0, 1000))
    assert by_ms[0].reason == "bird"
    assert by_ms[1000].reason == "skipped-duplicate"
    assert by_ms[5000].kept and by_ms[5000].reason == "bird-count-changed"
    assert by_ms[6000].reason == "skipped-duplicate"


def test_the_gap_is_measured_from_the_last_kept_bird_sample_not_the_last_bird_sample():
    by_ms = _by_ms(select_frames(_bird_run(6), 4.0, 0.0, 1000))
    assert _kept(list(by_ms.values())) == [0, 4000]


def test_the_budget_keeps_every_multi_bird_frame_before_single_bird_ones_and_thins_evenly():
    samples = [(i * 1000, 2 if i % 5 == 0 else 1, 0.9) for i in range(50)]  # 10 doubles, 40 singles
    decisions = select_frames(samples, min_gap_s=0.0, empty_share=0.0, max_frames=30)
    kept = _kept(decisions)
    assert len(kept) == 30
    assert {ms for ms, n, _ in samples if n == 2} <= set(kept)
    singles = [ms for ms in kept if (ms // 1000) % 5]
    assert len(singles) == 20
    spread = [b - a for a, b in zip(singles, singles[1:])]
    assert max(spread) <= 3000 + 1000  # at most one multi-bird frame in between
    assert singles[0] < 4000 and singles[-1] > 45000
    assert {d.reason for d in decisions if not d.kept} == {"skipped-budget"}


def test_more_multi_bird_frames_than_budget_are_thinned_evenly_and_no_single_bird_survives():
    samples = [(i * 1000, 2 if i % 2 == 0 else 1, 0.9) for i in range(40)]  # 20 doubles
    kept = _kept(select_frames(samples, 0.0, 0.0, max_frames=5))
    assert len(kept) == 5
    assert all((ms // 1000) % 2 == 0 for ms in kept)
    assert kept[0] < 8000 and kept[-1] > 30000


def test_the_budget_for_bird_frames_leaves_room_for_the_empty_share():
    samples = _bird_run(200, step=10_000) + [(5000 + i * 10_000, 0, 0.0) for i in range(200)]
    decisions = select_frames(samples, 4.0, empty_share=0.25, max_frames=100)
    birds = _kept(decisions, "bird", "bird-count-changed")
    empties = _kept(decisions, "empty", "near-miss")
    assert len(birds) == 75
    assert len(empties) == 25


def _birds_and_empties(n_birds=100, n_plain=400, near_conf=()):
    samples = [(i * 10_000, 1, 0.9) for i in range(n_birds)]
    samples += [(5000 + i * 10_000, 0, 0.0) for i in range(n_plain)]
    samples += [(5000 + (n_plain + i) * 10_000, 0, c) for i, c in enumerate(near_conf)]
    return samples


def test_the_empty_target_follows_the_empty_share():
    decisions = select_frames(_birds_and_empties(100, 400), 4.0, empty_share=0.2, max_frames=3000)
    assert len(_kept(decisions, "bird")) == 100
    assert len(_kept(decisions, "empty")) == 25  # round(100 * 0.2 / 0.8)
    assert not _kept(decisions, "near-miss")
    assert {d.reason for d in decisions if d.ms % 10_000 == 5000 and not d.kept} == {"skipped-empty"}


def test_kept_empty_frames_are_spread_over_the_video():
    kept = _kept(select_frames(_birds_and_empties(100, 400), 4.0, 0.2, 3000), "empty")
    gaps = [b - a for a, b in zip(kept, kept[1:])]
    assert max(gaps) <= 2 * min(gaps) + 10_000
    assert kept[0] < 4_000_000 * 0.1 and kept[-1] > 4_000_000 * 0.9


def test_near_misses_fill_at_most_half_of_the_empties_highest_confidence_first():
    conf = [0.05 + 0.001 * i for i in range(50)]
    decisions = select_frames(_birds_and_empties(100, 400, conf), 4.0, 0.2, 3000)
    near = _kept(decisions, "near-miss")
    assert len(near) == 12  # half of 25
    by_conf = sorted(((d.ms, c) for d, c in zip(
        [x for x in decisions if x.ms >= 5000 + 400 * 10_000], conf)), key=lambda t: -t[1])
    assert set(near) == {ms for ms, _ in by_conf[:12]}
    assert len(_kept(decisions, "empty")) == 13
    assert {d.reason for d in decisions if d.ms >= 5000 + 400 * 10_000 and not d.kept} == {"skipped-empty"}


def test_few_near_misses_leave_the_rest_to_plain_empties():
    decisions = select_frames(_birds_and_empties(100, 400, [0.1, 0.2, 0.3]), 4.0, 0.2, 3000)
    assert len(_kept(decisions, "near-miss")) == 3
    assert len(_kept(decisions, "empty")) == 22


def test_a_confident_low_score_below_the_floor_is_plain_empty_not_near_miss():
    samples = [(i * 1000, 0, 0.049) for i in range(30)]
    assert {d.reason for d in select_frames(samples, 4.0, 0.15, 100) if d.kept} == {"empty"}


def test_a_video_without_birds_keeps_the_empty_minimum():
    decisions = select_frames([(i * 1000, 0, 0.0) for i in range(100)], 4.0, 0.15, 3000)
    assert len(_kept(decisions)) == 20
    decisions = select_frames([(i * 1000, 0, 0.0) for i in range(8)], 4.0, 0.15, 3000)
    assert len(_kept(decisions)) == 8


def test_every_sample_gets_exactly_one_decision_in_time_order():
    samples = _birds_and_empties(30, 100, [0.07, 0.09])
    shuffled = samples[::-1]
    decisions = select_frames(shuffled, 4.0, 0.15, 60)
    assert [d.ms for d in decisions] == sorted(ms for ms, _, _ in samples)
    assert all(d.reason in {"bird", "bird-count-changed", "empty", "near-miss", "skipped-duplicate",
                            "skipped-budget", "skipped-empty"} for d in decisions)
    assert all(d.kept == (d.reason in {"bird", "bird-count-changed", "empty", "near-miss"}) for d in decisions)


def test_select_frames_is_deterministic():
    samples = _birds_and_empties(50, 200, [0.06, 0.06, 0.08])
    assert select_frames(samples, 4.0, 0.15, 80) == select_frames(list(samples), 4.0, 0.15, 80)


def test_select_frames_with_nothing_returns_nothing_and_a_full_empty_share_is_refused():
    assert select_frames([], 4.0, 0.15, 100) == []
    with pytest.raises(ValueError):
        select_frames([(0, 1, 0.9)], 4.0, 1.0, 100)


# highlight_segments ----------------------------------------------------------------------------

def _birds_at(*times, boxes=1):
    return [(round(t * 1000), boxes, 0.9) for t in times]


def test_highlights_merge_pad_and_clamp():
    samples = _birds_at(10, 11, 12, 30)
    assert highlight_segments(samples, 1.0, 2.0, 900, 100.0) == [(8.0, 14.0), (28.0, 32.0)]
    assert highlight_segments(_birds_at(0.5, 99.5), 1.0, 2.0, 900, 100.0) == [(0.0, 2.5), (97.5, 100.0)]


def test_highlight_samples_closer_than_two_pads_plus_every_are_merged():
    assert highlight_segments(_birds_at(10, 14), 1.0, 2.0, 900, 100.0) == [(8.0, 16.0)]
    assert highlight_segments(_birds_at(10, 15), 1.0, 2.0, 900, 100.0) == [(8.0, 12.0), (13.0, 17.0)]


def test_highlights_ignore_samples_without_birds_and_return_nothing_when_there_are_none():
    assert highlight_segments([(1000, 0, 0.0), (2000, 0, 0.09)], 1.0, 2.0, 900, 100.0) == []


def test_highlights_stop_at_the_total_cap_preferring_the_highest_peaks_and_stay_in_time_order():
    samples = _birds_at(10) + _birds_at(30, boxes=3) + _birds_at(50, boxes=2)  # each segment is 4 s
    assert highlight_segments(samples, 1.0, 2.0, 8.0, 100.0) == [(28.0, 32.0), (48.0, 52.0)]
    assert highlight_segments(samples, 1.0, 2.0, 100.0, 100.0) == [(8.0, 12.0), (28.0, 32.0), (48.0, 52.0)]


def test_a_segment_longer_than_the_cap_is_trimmed_to_it():
    segments = highlight_segments(_birds_at(*range(10, 40)), 1.0, 2.0, 10.0, 100.0)
    assert segments == [(8.0, 18.0)]


def test_the_peak_of_a_segment_counts_the_birds_inside_it():
    samples = _birds_at(10, 11) + _birds_at(12, boxes=4)
    assert mine_frames.peak_boxes(samples, 8.0, 14.0) == 4
    assert mine_frames.peak_boxes(samples, 20.0, 22.0) == 0


# end to end (OpenCV fallback, stub detector) ---------------------------------------------------

@pytest.fixture(autouse=True)
def _no_ffmpeg(monkeypatch):
    monkeypatch.setattr(mine_frames, "have_ffmpeg", lambda: False)


class Stub:
    """Hands out one scripted (n_boxes, max_conf) per sample, in the order the videos are scanned."""

    def __init__(self, script, imgsz=None):
        self.script, self.imgsz, self.seen = list(script), imgsz, 0

    def __call__(self, frames):
        if self.imgsz:
            assert all(max(f.shape[:2]) <= self.imgsz for f in frames)
        out = self.script[self.seen:self.seen + len(frames)]
        assert len(out) == len(frames)
        self.seen += len(frames)
        return out


SCRIPT = [(1, 0.9), (0, 0.0), (2, 0.8), (0, 0.07),  # train/a at 0 s, 1 s, 2 s, 3 s
          (0, 0.0), (1, 0.7), (0, 0.0)]  # demo/b at 0 s, 1 s, 2 s


@pytest.fixture
def two_videos(make_video, tmp_path):
    make_video("videos/train/a.mp4", seconds=4.0)
    make_video("videos/demo/b.mp4", seconds=3.0)
    return tmp_path / "videos", tmp_path / "frames"


def test_mining_writes_the_extract_frames_layout_and_one_csv_row_per_sample(two_videos):
    videos, out = two_videos
    mine_frames.main(["--videos", str(videos), "--out", str(out), "--scan-imgsz", "160", "--workers", "1"],
                     scan_fn=Stub(SCRIPT, imgsz=160))
    assert sorted(p.name for p in (out / "train" / "a").iterdir()) == [
        "a_00000000.jpg", "a_00001000.jpg", "a_00002000.jpg", "a_00003000.jpg"]
    assert sorted(p.name for p in (out / "demo" / "b").iterdir()) == [
        "b_00000000.jpg", "b_00001000.jpg", "b_00002000.jpg"]
    frame = cv2.imread(str(out / "train" / "a" / "a_00002000.jpg"))
    assert frame.shape == (240, 320, 3)  # full source resolution, not the scan size

    with (out / "mining.csv").open(newline="") as f:
        rows = list(csv.DictReader(f))
    assert list(rows[0]) == ["split", "video", "ms", "n_boxes", "max_conf", "kept", "reason"]
    assert [(r["split"], r["video"], int(r["ms"])) for r in rows] == [
        ("train", "a", 0), ("train", "a", 1000), ("train", "a", 2000), ("train", "a", 3000),
        ("demo", "b", 0), ("demo", "b", 1000), ("demo", "b", 2000)]
    assert [r["reason"] for r in rows] == ["bird", "empty", "bird-count-changed", "near-miss",
                                           "empty", "bird", "empty"]
    assert [int(r["n_boxes"]) for r in rows] == [1, 0, 2, 0, 0, 1, 0]
    assert float(rows[2]["max_conf"]) == pytest.approx(0.8)
    assert {r["kept"] for r in rows} == {"True"}
    assert sorted(p.name for p in out.iterdir()) == ["demo", "mining.csv", "train"]  # no temp dirs left


def test_mining_prints_a_summary_per_video_and_in_total(two_videos, capsys):
    videos, out = two_videos
    mine_frames.main(["--videos", str(videos), "--out", str(out), "--workers", "1"], scan_fn=Stub(SCRIPT))
    text = capsys.readouterr().out
    assert "train/a.mp4:" in text and "demo/b.mp4:" in text and "total:" in text
    assert "4 scanned" in text and "7 scanned" in text
    assert "50%" in text  # a: 2 of 4 samples had a bird


def test_mining_with_a_process_pool_gives_the_same_frames(two_videos):
    videos, out = two_videos
    mine_frames.main(["--videos", str(videos), "--out", str(out), "--workers", "2"], scan_fn=Stub(SCRIPT))
    assert len(list(out.rglob("*.jpg"))) == 7


def test_mining_thins_a_still_bird_and_records_why(make_video, tmp_path):
    make_video("videos/train/a.mp4", seconds=12.0)
    out = tmp_path / "frames"
    mine_frames.main(["--videos", str(tmp_path / "videos"), "--out", str(out), "--workers", "1",
                      "--min-gap-s", "4", "--empty-share", "0"], scan_fn=Stub([(1, 0.9)] * 12))
    with (out / "mining.csv").open(newline="") as f:
        rows = list(csv.DictReader(f))
    assert [r["ms"] for r in rows if r["kept"] == "True"] == ["0", "4000", "8000"]
    assert {r["reason"] for r in rows if r["kept"] == "False"} == {"skipped-duplicate"}
    assert len(list(out.rglob("*.jpg"))) == 3


def test_frames_are_read_at_the_requested_millisecond(tmp_path):
    path = tmp_path / "steps.mp4"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10, (160, 120))
    for second in range(4):
        for _ in range(10):
            writer.write(np.full((120, 160, 3), 40 + 60 * second, dtype=np.uint8))
    writer.release()
    out = tmp_path / "out"
    assert mine_frames.write_frames(path, out, [2500, 500]) == 2
    assert abs(float(cv2.imread(str(out / "steps_00002500.jpg")).mean()) - 160) < 12
    assert abs(float(cv2.imread(str(out / "steps_00000500.jpg")).mean()) - 40) < 12


def test_highlights_clip_and_its_segment_list_are_written(two_videos):
    videos, out = two_videos
    clip = out.parent / "busy.mp4"
    mine_frames.main(["--videos", str(videos), "--out", str(out), "--workers", "1",
                      "--highlights", str(clip), "--highlights-from", "a", "--pad-s", "1"],
                     scan_fn=Stub(SCRIPT))
    cap = cv2.VideoCapture(str(clip))
    assert cap.isOpened()
    assert (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))) == (320, 240)
    assert abs(cap.get(cv2.CAP_PROP_FRAME_COUNT) - 30) <= 2  # birds at 0 s and 2 s, pad 1 s: 0 s to 3 s
    ok, _ = cap.read()
    assert ok
    cap.release()
    with Path(f"{clip}.segments.csv").open(newline="") as f:
        rows = list(csv.DictReader(f))
    assert list(rows[0]) == ["start_s", "end_s", "peak_boxes"]
    assert [(float(r["start_s"]), float(r["end_s"]), int(r["peak_boxes"])) for r in rows] == [(0.0, 3.0, 2)]


def _refuses(argv, capsys, scan_fn=None):
    def boom(frames):
        raise AssertionError("must not scan")

    with pytest.raises(SystemExit) as exit_info:
        mine_frames.main(argv, scan_fn=scan_fn or boom)
    assert exit_info.value.code == 2
    return capsys.readouterr().err


def test_two_videos_with_one_stem_exit_2_and_write_nothing(make_video, tmp_path, capsys):
    make_video("videos/train/x/a.mp4")
    make_video("videos/demo/a.mp4")
    out = tmp_path / "frames"
    err = _refuses(["--videos", str(tmp_path / "videos"), "--out", str(out)], capsys)
    assert "train/x/a.mp4" in err and "demo/a.mp4" in err
    assert not out.exists() or not list(out.rglob("*"))


def test_no_videos_exit_2(tmp_path, capsys):
    (tmp_path / "videos" / "train").mkdir(parents=True)
    err = _refuses(["--videos", str(tmp_path / "videos"), "--out", str(tmp_path / "f")], capsys)
    assert "no videos" in err.lower()


def test_highlights_need_a_known_stem(two_videos, capsys):
    videos, out = two_videos
    base = ["--videos", str(videos), "--out", str(out), "--highlights", str(out.parent / "x.mp4")]
    assert "--highlights-from" in _refuses(base, capsys)
    assert "nope" in _refuses(base + ["--highlights-from", "nope"], capsys)
    assert not out.exists()


def test_the_module_imports_without_ultralytics_or_torch():
    code = ("import sys; sys.path.insert(0, 'tools'); import mine_frames; "
            "assert 'ultralytics' not in sys.modules and 'torch' not in sys.modules, 'heavy import'")
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_the_ffmpeg_path_runs_the_expected_command_and_names_samples_by_time(tmp_path, monkeypatch):
    """A fake ffmpeg stands in for the real one: this checks our plumbing, not ffmpeg's filters."""
    fake = tmp_path / "bin" / "ffmpeg"
    fake.parent.mkdir()
    fake.write_text(f"#!{sys.executable}\n"
                    "import sys, cv2, numpy as np\n"
                    "args = sys.argv[1:]\n"
                    "open(args[-1].replace('%08d.jpg', 'args.txt'), 'w').write(' '.join(args))\n"
                    "for i in range(3):\n"
                    "    cv2.imwrite(args[-1] % i, np.zeros((54, 96, 3), np.uint8))\n")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake.parent}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setattr(mine_frames, "have_ffmpeg", lambda: True)
    dest = tmp_path / "scan"
    dest.mkdir()
    assert mine_frames.decode_samples(tmp_path / "x.mp4", 2.0, 960, dest) == [0, 2000, 4000]
    args = (dest / "args.txt").read_text()
    assert "fps=1/2" in args and "min(iw,960)" in args and str(dest / "%08d.jpg") in args
