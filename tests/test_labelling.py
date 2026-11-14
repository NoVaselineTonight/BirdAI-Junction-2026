import csv
import json

import cv2
import numpy as np
import pytest

import extract_frames
import review_sheets
from autolabel import decide_label, label_frame
from feeder_census.species import load_species


def test_two_teachers_agreeing_gives_an_automatic_label():
    assert decide_label("great_tit", 0.91, 0.74, "great_tit", True) == ("great_tit", "auto")


def test_disagreement_or_a_narrow_margin_goes_to_review():
    assert decide_label("tree_sparrow", 0.70, 0.40, "house_sparrow", True) == ("unidentified", "review")
    assert decide_label("tree_sparrow", 0.55, 0.10, "tree_sparrow", True) == ("unidentified", "review")
    assert decide_label("great_tit", 0.95, 0.80, None, True) == ("unidentified", "review")


def test_species_the_second_teacher_cannot_name_needs_a_high_score():
    assert decide_label("willow_tit", 0.90, 0.50, None, False) == ("willow_tit", "single")
    assert decide_label("willow_tit", 0.80, 0.50, None, False) == ("unidentified", "review")


def test_extract_frames_keeps_the_train_demo_split(make_video, tmp_path):
    make_video("videos/train/a.mp4", seconds=3.0)
    make_video("videos/demo/b.mp4", seconds=3.0)
    out = tmp_path / "frames"
    extract_frames.main(["--videos", str(tmp_path / "videos"), "--out", str(out), "--every", "1.0"])
    assert sorted(p.name for p in (out / "train" / "a").iterdir()) == [
        "a_00000000.jpg", "a_00001000.jpg", "a_00002000.jpg"]
    assert len(list((out / "demo" / "b").iterdir())) == 3


def test_extract_frames_stops_at_max_per_video(make_video, tmp_path):
    make_video("videos/train/a.mp4", seconds=10.0)
    out = tmp_path / "frames"
    extract_frames.main(["--videos", str(tmp_path / "videos"), "--out", str(out),
                         "--every", "1.0", "--max-per-video", "4"])
    assert len(list((out / "train" / "a").iterdir())) == 4


FRAME = np.zeros((240, 320, 3), dtype=np.uint8)
META = {"split": "train", "video": "a", "frame": "train/a/a_00000000.jpg"}
TWO_BOXES = [((10.0, 20.0, 110.0, 120.0), 0.9), ((150.0, 40.0, 250.0, 140.0), 0.5)]


def test_label_frame_writes_rows_for_birds_and_for_empty_frames():
    species = load_species()
    calls = []

    def bioclip(crops):
        calls.append([c.shape for c in crops])
        return [("great_tit", 0.91, 0.74)] * len(crops)

    def inat(crop, bioclip_species):
        return "great_tit", 0.66, True

    rows = label_frame(FRAME, META, lambda f: [], bioclip, inat, species)
    assert rows == [{"id": "a_00000000#-", "split": "train", "video": "a", "frame": "train/a/a_00000000.jpg",
                     "box": None, "label": None, "status": "empty"}]
    assert calls == []

    rows = label_frame(FRAME, META, lambda f: TWO_BOXES, bioclip, inat, species)
    assert [r["id"] for r in rows] == ["a_00000000#0", "a_00000000#1"] and rows[0]["status"] == "auto"
    assert calls == [[(100, 100, 3), (100, 100, 3)]]  # one batched call, crops cut at the boxes
    assert rows[1] == {
        "id": "a_00000000#1", "split": "train", "video": "a", "frame": "train/a/a_00000000.jpg",
        "box": [150.0, 40.0, 250.0, 140.0], "box_conf": 0.5,
        "bioclip": {"species": "great_tit", "score": 0.91, "margin": 0.74},
        "inat": {"species": "great_tit", "prob": 0.66},
        "label": "great_tit", "status": "auto"}
    json.dumps(rows)  # rows are plain JSON


def test_label_frame_sends_the_bioclip_species_to_the_second_teacher_and_decides_per_box():
    seen = []

    def bioclip(crops):
        return [("willow_tit", 0.90, 0.50), ("tree_sparrow", 0.80, 0.50)]

    def inat(crop, bioclip_species):
        seen.append(bioclip_species)
        return (None, 0.0, False) if bioclip_species == "willow_tit" else ("house_sparrow", 0.7, True)

    rows = label_frame(FRAME, META, lambda f: TWO_BOXES, bioclip, inat, load_species())
    assert seen == ["willow_tit", "tree_sparrow"]
    assert [(r["label"], r["status"]) for r in rows] == [("willow_tit", "single"), ("unidentified", "review")]
    assert rows[0]["inat"] == {"species": None, "prob": 0.0}


def test_label_frame_clips_boxes_that_leave_the_frame():
    seen = []

    def bioclip(crops):
        seen.extend(c.shape for c in crops)
        return [("great_tit", 0.9, 0.5)] * len(crops)

    boxes = [((-20.0, -5.0, 60.0, 50.0), 0.8), ((300.0, 200.0, 400.0, 300.0), 0.8)]
    label_frame(FRAME, META, lambda f: boxes, bioclip, lambda c, s: (s, 0.5, True), load_species())
    assert seen == [(50, 60, 3), (40, 20, 3)]


def test_label_frame_rejects_a_species_that_is_not_in_the_species_list():
    with pytest.raises(ValueError, match="dodo"):
        label_frame(FRAME, META, lambda f: TWO_BOXES[:1], lambda crops: [("dodo", 0.9, 0.5)],
                    lambda c, s: (None, 0.0, False), load_species())


def _write_labels(path, n):
    rows = []
    for i in range(n):
        rows.append({"id": f"v_{i:08d}#0", "split": "train", "video": "v", "frame": f"train/v/v_{i:08d}.jpg",
                     "box": [10.0, 10.0, 90.0, 70.0], "box_conf": 0.9,
                     "bioclip": {"species": "great_tit", "score": 0.9, "margin": 0.5},
                     "inat": {"species": "great_tit", "prob": 0.6},
                     "label": "great_tit", "status": "auto"})
    rows.append({"id": "v_99999999#-", "split": "train", "video": "v", "frame": "train/v/v_99999999.jpg",
                 "box": None, "label": None, "status": "empty"})
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def test_review_sheets_hold_48_crops_and_an_index(tmp_path):
    frames, out = tmp_path / "frames", tmp_path / "review"
    (frames / "train" / "v").mkdir(parents=True)
    img = np.full((120, 160, 3), 90, dtype=np.uint8)
    for i in range(100):
        cv2.imwrite(str(frames / "train" / "v" / f"v_{i:08d}.jpg"), img)
    labels = tmp_path / "auto.jsonl"
    _write_labels(labels, 100)

    review_sheets.main(["--labels", str(labels), "--frames", str(frames), "--out", str(out)])

    assert sorted(p.name for p in (out / "great_tit").iterdir()) == [
        "great_tit_01.jpg", "great_tit_02.jpg", "great_tit_03.jpg"]
    sheet = cv2.imread(str(out / "great_tit" / "great_tit_01.jpg"))
    assert sheet.shape[:2] == (6 * 160, 8 * 160)
    with open(out / "index.csv", newline="") as f:
        rows = list(csv.reader(f))
    assert rows[0] == ["n", "id", "label", "status", "bioclip", "inat"]
    assert len(rows) == 101  # header and 100 boxes; the empty frame has no crop
    assert rows[1] == ["1", "v_00000000#0", "great_tit", "auto", "great_tit", "great_tit"]
    assert rows[49][0] == "49"  # numbering continues on the second sheet
    assert (out / "corrections.csv").read_text() == "id,label\n"


def test_review_sheets_keep_existing_corrections(tmp_path):
    frames, out = tmp_path / "frames", tmp_path / "review"
    (frames / "train" / "v").mkdir(parents=True)
    cv2.imwrite(str(frames / "train" / "v" / "v_00000000.jpg"), np.zeros((120, 160, 3), np.uint8))
    out.mkdir()
    (out / "corrections.csv").write_text("id,label\nv_00000000#0,drop\n")
    labels = tmp_path / "auto.jsonl"
    _write_labels(labels, 1)
    review_sheets.main(["--labels", str(labels), "--frames", str(frames), "--out", str(out)])
    assert (out / "corrections.csv").read_text() == "id,label\nv_00000000#0,drop\n"
