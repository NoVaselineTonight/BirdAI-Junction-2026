import csv
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures.process import BrokenProcessPool
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


def test_a_video_of_only_near_misses_still_keeps_the_empty_minimum():
    samples = [(i * 1000, 0, 0.06 + 0.001 * i) for i in range(30)]
    kept = select_frames(samples, 4.0, 0.15, 3000)
    assert len(_kept(kept)) == 20
    assert {d.reason for d in kept if d.kept} == {"near-miss"}
    assert set(_kept(kept)) == {i * 1000 for i in range(10, 30)}  # the most bird-like ones


def test_near_misses_top_up_the_target_when_plain_empties_run_out_highest_confidence_first():
    conf = [0.05 + 0.001 * i for i in range(50)]
    decisions = select_frames(_birds_and_empties(100, 5, conf), 4.0, 0.2, 3000)  # target 25
    near_start = 5000 + 5 * 10_000
    near = _kept(decisions, "near-miss")
    assert len(near) == 20 and len(_kept(decisions, "empty")) == 5
    assert set(near) == {near_start + i * 10_000 for i in range(30, 50)}


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


# pure helpers of the two passes -----------------------------------------------------------------

def test_frame_index_and_millisecond_convert_back_and_forth_for_common_frame_rates():
    for fps in (10, 25, 30, 30000 / 1001, 59.94):
        for index in (0, 1, 7, 1000, 86_399, 2_700_000):
            assert mine_frames.ms_to_frame(mine_frames.frame_to_ms(index, fps), fps) == index


def test_check_times_picks_first_last_and_three_in_between():
    assert mine_frames.check_times(list(range(100, 200))) == [100, 124, 149, 174, 199]
    assert mine_frames.check_times([5, 7]) == [5, 7]
    assert mine_frames.check_times([]) == []


def _picture():
    img = np.zeros((480, 640, 3), np.uint8)
    img[:, :, 0] = np.linspace(0, 255, 640, dtype=np.uint8)[None, :]
    img[100:300, 200:400, 1] = 220
    img[350:450, 50:150, 2] = 180
    return img


def _jpeg(img, quality=92):
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)


def test_frames_match_is_small_for_the_same_picture_at_two_sizes_and_large_for_another_one():
    big = _jpeg(_picture())
    small = _jpeg(cv2.resize(_picture(), (160, 120), interpolation=cv2.INTER_AREA), 90)
    assert mine_frames.frames_match(big, small) < mine_frames.CHECK_THRESHOLD / 3
    assert mine_frames.frames_match(big, _jpeg(255 - _picture())) > mine_frames.CHECK_THRESHOLD * 3


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
    assert list(rows[0]) == ["split", "video", "ms", "n_boxes", "max_conf", "kept", "reason", "check_diff"]
    assert [(r["split"], r["video"], int(r["ms"])) for r in rows] == [
        ("train", "a", 0), ("train", "a", 1000), ("train", "a", 2000), ("train", "a", 3000),
        ("demo", "b", 0), ("demo", "b", 1000), ("demo", "b", 2000)]
    assert [r["reason"] for r in rows] == ["bird", "empty", "bird-count-changed", "near-miss",
                                           "empty", "bird", "empty"]
    assert [int(r["n_boxes"]) for r in rows] == [1, 0, 2, 0, 0, 1, 0]
    assert float(rows[2]["max_conf"]) == pytest.approx(0.8)
    assert {r["kept"] for r in rows} == {"True"}
    checked = [float(r["check_diff"]) for r in rows if r["check_diff"]]
    assert checked and all(d < mine_frames.CHECK_THRESHOLD / 2 for d in checked)  # saved frame is the scanned one
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
    assert mine_frames.write_frames(path, out, [2500, 500]) == [500, 2500]
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
    assert mine_frames.decode_samples(tmp_path / "x.mp4", 2.0, 960, dest, True) == [0, 2000, 4000]
    args = (dest / "args.txt").read_text()
    assert "fps=1/2" in args and "min(iw,960)" in args and str(dest / "%08d.jpg") in args


# fault handling --------------------------------------------------------------------------------

def _fake_ffmpeg(tmp_path, monkeypatch, mode):
    """mode: good | broken (always fails) | decode-fails (the 2 s self-test passes, sampling fails)."""
    fake = tmp_path / "bin" / "ffmpeg"
    fake.parent.mkdir(exist_ok=True)
    fake.write_text(f"#!{sys.executable}\n"
                    "import sys, cv2, numpy as np\n"
                    "args = sys.argv[1:]\n"
                    f"mode = {mode!r}\n"
                    "if mode == 'broken' or (mode == 'decode-fails' and '-t' not in args):\n"
                    "    sys.stderr.write('Unrecognized option boom\\n')\n"
                    "    sys.exit(1)\n"
                    "if '-ss' in args:\n"
                    "    cv2.imwrite(args[-1], np.zeros((240, 320, 3), np.uint8))\n"
                    "else:\n"
                    "    for i in range(3):\n"
                    "        cv2.imwrite(args[-1] % i, np.zeros((54, 96, 3), np.uint8))\n")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake.parent}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setattr(mine_frames, "have_ffmpeg", lambda: True)


def _rows(out):
    with (out / "mining.csv").open(newline="") as f:
        return list(csv.DictReader(f))


def _exit_code(argv, scan_fn):
    with pytest.raises(SystemExit) as exit_info:
        mine_frames.main(argv, scan_fn=scan_fn)
    return exit_info.value.code


def test_with_ffmpeg_both_passes_use_it_and_the_check_passes(make_video, tmp_path, monkeypatch):
    _fake_ffmpeg(tmp_path, monkeypatch, "good")
    make_video("videos/train/a.mp4", seconds=4.0)
    out = tmp_path / "frames"
    mine_frames.main(["--videos", str(tmp_path / "videos"), "--out", str(out), "--workers", "1"],
                     scan_fn=Stub([(1, 0.9), (0, 0.0), (0, 0.0)]))
    assert sorted(p.name for p in (out / "train" / "a").iterdir()) == [
        "a_00000000.jpg", "a_00001000.jpg", "a_00002000.jpg"]
    assert {r["check_diff"] for r in _rows(out)} == {"0.00"}


def test_when_ffmpeg_fails_the_video_is_failed_without_an_opencv_fallback(make_video, tmp_path, monkeypatch, capsys):
    _fake_ffmpeg(tmp_path, monkeypatch, "decode-fails")
    make_video("videos/train/a.mp4", seconds=4.0)
    out = tmp_path / "frames"
    assert _exit_code(["--videos", str(tmp_path / "videos"), "--out", str(out), "--workers", "1"], Stub([])) == 1
    err = capsys.readouterr().err
    assert "train/a.mp4" in err and "boom" in err
    assert not list(out.rglob("*.jpg"))
    assert _rows(out) == []


def test_a_failing_ffmpeg_self_test_stops_the_run_with_exit_2_before_any_scan(make_video, tmp_path, monkeypatch, capsys):
    _fake_ffmpeg(tmp_path, monkeypatch, "broken")
    make_video("videos/train/a.mp4")
    out = tmp_path / "frames"
    err = _refuses(["--videos", str(tmp_path / "videos"), "--out", str(out)], capsys)
    assert "ffmpeg" in err and "boom" in err
    assert not out.exists()


@pytest.mark.parametrize("flag", ["--every", "--scan-imgsz", "--max-per-video"])
def test_non_positive_numbers_exit_2(flag, two_videos, capsys):
    videos, out = two_videos
    err = _refuses(["--videos", str(videos), "--out", str(out), flag, "0"], capsys)
    assert flag in err
    assert not out.exists()


def _patched_decode(monkeypatch, after):
    real = mine_frames.decode_samples

    def decode(video, every, imgsz, dest, use_ffmpeg):
        times = real(video, every, imgsz, dest, use_ffmpeg)
        return after(video, dest, times)

    monkeypatch.setattr(mine_frames, "decode_samples", decode)


def test_a_frame_that_cannot_be_written_is_recorded_and_fails_the_run(make_video, tmp_path, monkeypatch, capsys):
    make_video("videos/train/a.mp4", seconds=3.0)

    def add_far_sample(video, dest, times):  # a sample 99 s into a 3 s clip: the seek finds nothing
        shutil.copy(dest / "00000000.jpg", dest / f"{len(times):08d}.jpg")
        return times + [99_000]

    _patched_decode(monkeypatch, add_far_sample)
    out = tmp_path / "frames"
    code = _exit_code(["--videos", str(tmp_path / "videos"), "--out", str(out), "--workers", "1",
                       "--min-gap-s", "0", "--empty-share", "0"], Stub([(1, 0.9)] * 4))
    assert code == 1
    rows = {int(r["ms"]): r for r in _rows(out)}
    assert (rows[99_000]["kept"], rows[99_000]["reason"]) == ("False", "write-failed")
    assert rows[1000]["kept"] == "True"
    assert sorted(p.name for p in (out / "train" / "a").iterdir()) == [
        "a_00000000.jpg", "a_00001000.jpg", "a_00002000.jpg"]
    assert "write-failed" in capsys.readouterr().out


def test_scanned_images_that_do_not_match_the_saved_frames_fail_the_video(make_video, tmp_path, monkeypatch, capsys):
    make_video("videos/train/a.mp4", seconds=4.0)

    def whiten(video, dest, times):  # the scan saw other pictures than pass 2 will read
        for path in dest.glob("*.jpg"):
            cv2.imwrite(str(path), np.full((120, 160, 3), 255, np.uint8))
        return times

    _patched_decode(monkeypatch, whiten)
    out = tmp_path / "frames"
    code = _exit_code(["--videos", str(tmp_path / "videos"), "--out", str(out), "--workers", "1"],
                      Stub(SCRIPT[:4]))
    assert code == 1
    err = capsys.readouterr().err
    assert "train/a.mp4" in err and "do not match" in err
    assert all(float(r["check_diff"]) > mine_frames.CHECK_THRESHOLD for r in _rows(out) if r["check_diff"])


def test_an_unreadable_sample_is_recorded_and_not_scanned(make_video, tmp_path, monkeypatch):
    make_video("videos/train/a.mp4", seconds=4.0)

    def truncate(video, dest, times):
        (dest / "00000001.jpg").write_bytes(b"\xff\xd8 not a jpeg")
        return times

    _patched_decode(monkeypatch, truncate)
    out = tmp_path / "frames"
    stub = Stub([(1, 0.9), (0, 0.0), (0, 0.0)])  # three scans for four samples
    mine_frames.main(["--videos", str(tmp_path / "videos"), "--out", str(out), "--workers", "1"], scan_fn=stub)
    rows = {int(r["ms"]): r for r in _rows(out)}
    assert (rows[1000]["kept"], rows[1000]["reason"]) == ("False", "unreadable")
    assert len(rows) == 4 and stub.seen == 3
    assert not (out / "train" / "a" / "a_00001000.jpg").exists()


def test_one_video_failing_does_not_stop_the_others_but_the_run_exits_1(make_video, tmp_path, monkeypatch, capsys):
    make_video("videos/train/a.mp4", seconds=3.0)
    make_video("videos/demo/b.mp4", seconds=3.0)
    real = mine_frames.decode_samples

    def decode(video, every, imgsz, dest, use_ffmpeg):
        if video.stem == "a":
            raise RuntimeError("decoder blew up")
        return real(video, every, imgsz, dest, use_ffmpeg)

    monkeypatch.setattr(mine_frames, "decode_samples", decode)
    out = tmp_path / "frames"
    assert _exit_code(["--videos", str(tmp_path / "videos"), "--out", str(out), "--workers", "1"],
                      Stub([(1, 0.9), (0, 0.0), (0, 0.0)])) == 1
    err = capsys.readouterr().err
    assert "train/a.mp4" in err and "decoder blew up" in err
    assert len(list((out / "demo" / "b").iterdir())) == 3
    assert [r["video"] for r in _rows(out)] == ["b", "b", "b"]


# a dead worker and a failing video do not abort the run -----------------------------------------

def _double_or_die(x):
    if x == "die":
        os._exit(1)  # like an OOM kill: no exception, the process is just gone
    return x * 2


def test_a_runner_survives_a_dead_worker_and_reports_the_task_that_died():
    runner = mine_frames.Runner(2)
    try:
        dead = runner.submit(_double_or_die, "die")
        with pytest.raises(BrokenProcessPool):
            dead.result()
        assert runner.submit(_double_or_die, 3).result() == 6  # a fresh pool took over
        assert [runner.submit(_double_or_die, i).result() for i in (1, 2)] == [2, 4]
        assert runner.rebuilds == 1
    finally:
        runner.close()


def test_a_runner_gives_up_after_three_rebuilds_with_a_clear_reason():
    runner = mine_frames.Runner(2)
    try:
        for _ in range(4):  # the first pool and three rebuilt ones all die
            with pytest.raises(BrokenProcessPool):
                runner.submit(_double_or_die, "die").result()
        assert runner.rebuilds == 3
        for _ in range(2):
            with pytest.raises(RuntimeError, match="worker pool kept dying"):
                runner.submit(_double_or_die, 1).result()
    finally:
        runner.close()


_real_decode = mine_frames.decode_samples


def _decode_or_die(video, every, imgsz, dest, use_ffmpeg):
    if video.stem == "b":
        time.sleep(0.6)  # lets the neighbouring videos finish first, so only b is lost
        os._exit(1)
    return _real_decode(video, every, imgsz, dest, use_ffmpeg)


def test_a_worker_dying_in_a_run_fails_only_its_video_and_the_run_carries_on(make_video, tmp_path, monkeypatch, capsys):
    for name in ("train/a", "train/b", "demo/c", "demo/d"):
        make_video(f"videos/{name}.mp4", seconds=3.0)
    monkeypatch.setattr(mine_frames, "decode_samples", _decode_or_die)
    out = tmp_path / "frames"
    code = _exit_code(["--videos", str(tmp_path / "videos"), "--out", str(out), "--workers", "2"],
                      Stub([(1, 0.9), (0, 0.0), (0, 0.0)] * 3))
    assert code == 1
    err = capsys.readouterr().err
    assert "train/b.mp4" in err and "1 problem" in err
    assert sorted(p.name for p in out.rglob("*.jpg")) == sorted(
        f"{v}_{ms:08d}.jpg" for v in "acd" for ms in (0, 1000, 2000))
    assert [r["video"] for r in _rows(out)] == ["a"] * 3 + ["c"] * 3 + ["d"] * 3


def test_an_exception_while_finishing_one_video_fails_only_that_video(make_video, tmp_path, monkeypatch, capsys):
    make_video("videos/train/a.mp4", seconds=3.0)
    make_video("videos/demo/b.mp4", seconds=3.0)
    real = mine_frames.finish_video

    def finish(p, out, table, failures):
        if p.video.stem == "a":
            raise RuntimeError("cv2 blew up")
        return real(p, out, table, failures)

    monkeypatch.setattr(mine_frames, "finish_video", finish)
    out = tmp_path / "frames"
    code = _exit_code(["--videos", str(tmp_path / "videos"), "--out", str(out), "--workers", "1"],
                      Stub([(1, 0.9), (0, 0.0), (0, 0.0)] * 2))
    assert code == 1
    err = capsys.readouterr().err
    assert "train/a.mp4" in err and "cv2 blew up" in err
    assert len(list((out / "demo" / "b").iterdir())) == 3
    assert [r["video"] for r in _rows(out)] == ["b"] * 3
