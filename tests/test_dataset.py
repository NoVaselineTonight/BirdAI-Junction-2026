import json
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

from build_dataset import apply_corrections, carve_validation, choose_classes

ROOT = Path(__file__).resolve().parent.parent
BOX = [100.0, 100.0, 300.0, 300.0]  # the centre quarter of a 400x400 frame


def row(id, label, split="train", box=BOX, status="auto"):
    stem = id.split("#")[0]
    video = stem.rsplit("_", 1)[0]
    return {"id": id, "split": split, "video": video, "frame": f"{split}/{video}/{stem}.jpg",
            "box": box, "label": label, "status": status}


def make_rows(tmp_path, groups):
    """groups: (split, video, label, n). One 400x400 frame and one box per entry; returns the rows."""
    rows = []
    for split, video, label, n in groups:
        for i in range(n):
            stem = f"{video}_{i * 1000:08d}"
            path = tmp_path / "frames" / split / video / f"{stem}.jpg"
            path.parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(path), np.full((400, 400, 3), 90, np.uint8))
            rows.append(row(f"{stem}#0", label, split))
    return rows


def run_build(tmp_path, rows, corrections=None, extra=()):
    labels = tmp_path / "auto.jsonl"
    labels.write_text("".join(json.dumps(r) + "\n" for r in rows))
    csv_path = tmp_path / "corrections.csv"
    csv_path.write_text("id,label\n" + "".join(f"{k},{v}\n" for k, v in (corrections or {}).items()))
    out = tmp_path / "dataset"
    return subprocess.run(
        [sys.executable, str(ROOT / "tools" / "build_dataset.py"), "--labels", str(labels),
         "--corrections", str(csv_path), "--frames", str(tmp_path / "frames"), "--out", str(out), *extra],
        capture_output=True, text=True)


def test_choose_classes_keeps_species_with_enough_boxes():
    counts = {"great_tit": 400, "blue_tit": 61, "bullfinch": 59, "unidentified": 900}
    assert choose_classes(counts, min_boxes=60) == ["great_tit", "blue_tit", "unidentified"]


def test_choose_classes_always_ends_with_unidentified():
    assert choose_classes({"great_tit": 5}, min_boxes=60) == ["unidentified"]


def test_corrections_relabel_and_drop():
    rows = [row("a#0", "great_tit"), row("a#1", "great_tit"), row("a#2", "unidentified")]
    out = apply_corrections(rows, {"a#0": "blue_tit", "a#1": "drop", "a#2": "willow_tit"})
    assert [(r["id"], r["label"]) for r in out] == [("a#0", "blue_tit"), ("a#2", "willow_tit")]
    assert [r["status"] for r in out] == ["corrected", "corrected"]
    assert rows[0]["label"] == "great_tit"  # the input rows are left alone


def test_corrections_for_unknown_ids_warn_on_stderr(capsys):
    out = apply_corrections([row("a#0", "great_tit")], {"zzz#9": "blue_tit"})
    assert [r["label"] for r in out] == ["great_tit"]
    assert "zzz#9" in capsys.readouterr().err


def test_dataset_split_follows_the_footage_and_rare_species_become_unidentified(tmp_path):
    rows = make_rows(tmp_path, [("train", "g", "great_tit", 70), ("train", "b", "blue_tit", 65),
                                ("train", "bf", "bullfinch", 5), ("demo", "d", "great_tit", 10)])
    done = run_build(tmp_path, rows)
    assert done.returncode == 0, done.stderr
    out = tmp_path / "dataset"
    assert json.loads((out / "classes.json").read_text()) == ["great_tit", "blue_tit", "unidentified"]
    for split in ("train", "val"):
        assert not any("demo" in p.name or p.name.startswith("d_") for p in (out / "images" / split).iterdir())
    assert len(list((out / "images" / "test").iterdir())) == 10
    # 70 and 65 frames lose their last ceil(15%) = 11 and 10 to val; the 5-frame video stays whole
    assert len(list((out / "images" / "val").iterdir())) == 21
    assert len(list((out / "images" / "train").iterdir())) == 59 + 55 + 5
    assert (out / "labels" / "test" / "d_00000000.txt").read_text().splitlines()[0] == "0 0.500000 0.500000 0.500000 0.500000"
    bullfinch_frame_label = (out / "labels" / "train" / "bf_00000000.txt").read_text()
    assert bullfinch_frame_label.startswith("2 ")
    assert (out / "images" / "test" / "d_00000000.jpg").is_file()


def test_validation_is_the_tail_of_each_long_training_video(tmp_path):
    rows = make_rows(tmp_path, [("train", "g", "great_tit", 20), ("train", "h", "great_tit", 50),
                                ("train", "b", "blue_tit", 65), ("train", "s", "blue_tit", 9),
                                ("demo", "d", "great_tit", 1)])
    done = run_build(tmp_path, rows)
    assert done.returncode == 0, done.stderr
    out = tmp_path / "dataset" / "images"
    val = sorted(p.stem for p in (out / "val").iterdir())
    assert [s for s in val if s.startswith("g_")] == ["g_00017000", "g_00018000", "g_00019000"]
    assert not any(s.startswith("s_") for s in val)  # 9 frames: too short to hold any back
    assert (out / "train" / "g_00016000.jpg").is_file() and not (out / "train" / "g_00017000.jpg").is_file()
    assert len([s for s in val if s.startswith("h_")]) == 8  # ceil(7.5)


def test_val_fraction_option_changes_the_tail(tmp_path):
    rows = make_rows(tmp_path, [("train", "g", "great_tit", 70), ("train", "b", "blue_tit", 65),
                                ("demo", "d", "great_tit", 1)])
    done = run_build(tmp_path, rows, extra=["--val-fraction", "0.5"])
    assert done.returncode == 0, done.stderr
    assert len([p for p in (tmp_path / "dataset" / "images" / "val").iterdir() if p.name.startswith("g_")]) == 35


def test_carve_validation_leaves_short_videos_and_demo_alone():
    frames = {f"train/v/v_{i * 500:08d}.jpg": "train" for i in range(10)}
    frames.update({f"train/w/w_{i * 500:08d}.jpg": "train" for i in range(9)})
    frames["demo/d/d_00000000.jpg"] = "demo"
    where = carve_validation(frames, 0.15)
    assert sorted(f for f, w in where.items() if w == "val") == ["train/v/v_00004000.jpg", "train/v/v_00004500.jpg"]
    assert where["demo/d/d_00000000.jpg"] == "test"
    assert all(w == "train" for f, w in where.items() if "/w/" in f)


def test_data_yaml_and_class_table(tmp_path):
    rows = make_rows(tmp_path, [("train", "g", "great_tit", 70), ("train", "b", "blue_tit", 65),
                                ("demo", "d", "great_tit", 3)])
    done = run_build(tmp_path, rows)
    assert done.returncode == 0, done.stderr
    out = tmp_path / "dataset"
    assert (out / "data.yaml").read_text().splitlines() == [
        f"path: {out.resolve()}", "train: images/train", "val: images/val", "test: images/test", "names:",
        "  0: great_tit", "  1: blue_tit", "  2: unidentified"]
    table = done.stdout.splitlines()
    assert any(line.split() == ["great_tit", "59", "11", "3"] for line in table)
    assert any(line.split() == ["blue_tit", "55", "10", "0"] for line in table)
    assert any(line.split() == ["unidentified", "0", "0", "0"] for line in table)


def test_corrections_change_the_dataset_and_empty_frames_get_an_empty_label(tmp_path):
    rows = make_rows(tmp_path, [("train", "g", "great_tit", 70), ("train", "b", "blue_tit", 65),
                                ("train", "x", "great_tit", 2), ("demo", "d", "great_tit", 1)])
    rows.append({"id": "e_00000000#-", "split": "train", "video": "e", "frame": "train/e/e_00000000.jpg",
                 "box": None, "label": None, "status": "empty"})
    (tmp_path / "frames" / "train" / "e").mkdir()
    cv2.imwrite(str(tmp_path / "frames/train/e/e_00000000.jpg"), np.zeros((400, 400, 3), np.uint8))
    done = run_build(tmp_path, rows, {"x_00000000#0": "blue_tit", "x_00001000#0": "drop", "nope#1": "blue_tit"})
    assert done.returncode == 0, done.stderr
    assert "nope#1" in done.stderr
    out = tmp_path / "dataset" / "labels" / "train"
    assert (out / "x_00000000.txt").read_text().startswith("1 ")
    assert (out / "x_00001000.txt").read_text() == ""  # every box dropped: the frame stays as a negative
    assert (out / "e_00000000.txt").read_text() == ""


def test_unknown_correction_label_is_refused(tmp_path):
    rows = make_rows(tmp_path, [("train", "g", "great_tit", 70), ("demo", "d", "great_tit", 1)])
    done = run_build(tmp_path, rows, {"g_00000000#0": "great_titt"})
    assert done.returncode == 2
    assert "great_titt" in done.stderr


def test_build_refuses_without_held_out_footage(tmp_path):
    rows = make_rows(tmp_path, [("train", "g", "great_tit", 70), ("train", "b", "blue_tit", 65)])
    done = run_build(tmp_path, rows)
    assert done.returncode == 2
    assert "no held-out footage: put the demo video in data/videos/demo" in done.stderr


def test_build_refuses_when_training_videos_are_too_short_to_hold_frames_back(tmp_path):
    groups = [("train", f"g{i}", "great_tit", 9) for i in range(8)] + [("train", f"b{i}", "blue_tit", 9) for i in range(8)]
    rows = make_rows(tmp_path, groups + [("demo", "d", "great_tit", 1)])
    done = run_build(tmp_path, rows)
    assert done.returncode == 2
    assert "no validation frames: training videos are too short to hold some back" in done.stderr


def test_build_refuses_with_fewer_than_two_species_classes(tmp_path):
    rows = make_rows(tmp_path, [("train", "g", "great_tit", 70), ("train", "b", "blue_tit", 20),
                                ("demo", "d", "great_tit", 1)])
    done = run_build(tmp_path, rows)
    assert done.returncode == 2
    assert "great_tit" in done.stderr and "70" in done.stderr and "blue_tit" in done.stderr and "20" in done.stderr
