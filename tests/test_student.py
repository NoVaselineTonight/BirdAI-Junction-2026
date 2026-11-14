import json
from pathlib import Path

import cv2
import numpy as np
import pytest

import train_student
from feeder_census.detectors import student
from feeder_census.detectors.student import StudentDetector, decode_student
from feeder_census.types import UNIDENTIFIED


def test_decode_student_undoes_the_letterbox():
    out = np.zeros((1, 300, 6), np.float32)
    out[0, 0] = [100, 240, 200, 340, 0.9, 0]  # 1920x1080 in a 640 letterbox: ratio 1/3, pad (0, 140)
    (d,) = decode_student(out, ratio=1 / 3, pad=(0, 140), classes=["great_tit", "unidentified"])
    assert d.species == "great_tit" and d.confidence == pytest.approx(0.9)
    assert d.box == pytest.approx((300, 300, 600, 600))


def test_student_never_gives_one_bird_two_species():
    out = np.zeros((1, 300, 6), np.float32)
    out[0, 0] = [100, 240, 200, 340, 0.8, 0]
    out[0, 1] = [102, 241, 201, 338, 0.6, 1]
    dets = decode_student(out, 1 / 3, (0, 140), ["great_tit", "blue_tit", "unidentified"])
    assert [d.species for d in dets] == ["great_tit"]


def test_student_merges_a_head_box_inside_a_body_box():
    out = np.zeros((1, 300, 6), np.float32)
    out[0, 0] = [100, 240, 300, 440, 0.8, 0]
    out[0, 1] = [120, 250, 160, 290, 0.6, 1]
    dets = decode_student(out, 1 / 3, (0, 140), ["great_tit", "blue_tit", "unidentified"])
    assert [d.species for d in dets] == ["great_tit"]


def test_unidentified_class_is_not_a_species():
    out = np.zeros((1, 300, 6), np.float32)
    out[0, 0] = [10, 150, 60, 200, 0.7, 1]
    (d,) = decode_student(out, 1 / 3, (0, 140), ["great_tit", "unidentified"])
    assert d.species == UNIDENTIFIED


def test_rows_under_min_score_are_dropped_and_padding_rows_do_not_matter():
    out = np.zeros((1, 300, 6), np.float32)
    out[0, 0] = [100, 240, 200, 340, 0.04, 0]
    assert decode_student(out, 1 / 3, (0, 140), ["great_tit", "unidentified"]) == []


def test_two_separate_birds_come_out_best_first():
    out = np.zeros((1, 300, 6), np.float32)
    out[0, 0] = [10, 150, 60, 200, 0.5, 0]
    out[0, 1] = [300, 250, 400, 350, 0.9, 1]
    dets = decode_student(out, 1 / 3, (0, 140), ["great_tit", "unidentified"])
    assert [d.confidence for d in dets] == pytest.approx([0.9, 0.5])


def test_output_with_the_wrong_row_width_is_refused():
    with pytest.raises(ValueError, match="6"):
        decode_student(np.zeros((1, 300, 84), np.float32), 1.0, (0, 0), ["great_tit", "unidentified"])


def test_a_class_index_outside_the_class_list_is_refused():
    out = np.zeros((1, 300, 6), np.float32)
    out[0, 0] = [10, 150, 60, 200, 0.7, 5]
    with pytest.raises(ValueError, match="class"):
        decode_student(out, 1 / 3, (0, 140), ["great_tit", "unidentified"])


class FakeSession:
    """Stands in for onnxruntime.InferenceSession: records the input and returns a fixed output."""

    last = None

    def __init__(self, path, providers=None):
        FakeSession.last = self
        self.providers = providers
        self.fed = None
        self.output = np.zeros((1, 300, 6), np.float32)

    def get_inputs(self):
        return [type("Input", (), {"name": "images"})()]

    def run(self, names, feeds):
        self.fed = feeds
        return [self.output]


@pytest.fixture
def card(tmp_path):
    path = tmp_path / "feeder.json"
    path.write_text(json.dumps({"name": "Feeder student 640", "kind": "student", "base": "yolo26n", "imgsz": 640,
                                "classes": ["great_tit", "blue_tit", "unidentified"], "count_threshold": 0.6,
                                "trained_at": "2026-11-14T10:00:00Z", "train_boxes": {}, "held_out_footage": [],
                                "metrics": None}))
    return path


@pytest.fixture
def detector(monkeypatch, card, tmp_path):
    monkeypatch.setattr(student.ort, "InferenceSession", FakeSession)
    return StudentDetector(tmp_path / "feeder.onnx", card)


def test_student_detector_reads_its_card(detector):
    assert detector.name == "Feeder student 640"
    assert detector.count_threshold == 0.6
    assert detector.species == ("great_tit", "blue_tit")
    assert FakeSession.last.providers == ["CPUExecutionProvider"]


def test_student_detector_feeds_a_letterboxed_rgb_float_image(detector):
    frame = np.zeros((1080, 1920, 3), np.uint8)
    frame[:, :] = (255, 0, 0)  # BGR blue
    detector.detect(frame)
    blob = FakeSession.last.fed["images"]
    assert blob.shape == (1, 3, 640, 640) and blob.dtype == np.float32
    assert blob[0, 2, 320, 320] == pytest.approx(1.0) and blob[0, 0, 320, 320] == pytest.approx(0.0)  # RGB: blue is channel 2
    assert blob[0, 0, 5, 5] == pytest.approx(114 / 255)  # padding above the picture


def test_student_detector_returns_boxes_in_frame_pixels_clipped_to_the_frame(detector):
    FakeSession.last.output[0, 0] = [100, 240, 200, 340, 0.9, 1]
    FakeSession.last.output[0, 1] = [600, 200, 700, 300, 0.8, 0]  # reaches past the right edge
    FakeSession.last.output[0, 2] = [-50, -50, -10, -10, 0.7, 0]  # entirely outside the frame
    dets = detector.detect(np.zeros((1080, 1920, 3), np.uint8))
    assert [d.species for d in dets] == ["blue_tit", "great_tit"]
    assert dets[0].box == pytest.approx((300, 300, 600, 600))
    assert dets[1].box == pytest.approx((1800, 180, 1920, 480))


def test_student_detector_drops_nothing_when_there_is_no_bird(detector):
    assert detector.detect(np.zeros((480, 640, 3), np.uint8)) == []


def test_build_detector_makes_a_student_from_a_directory(monkeypatch, card, tmp_path):
    from feeder_census.detectors import build_detector
    from feeder_census.species import load_species

    monkeypatch.setattr(student.ort, "InferenceSession", FakeSession)
    (tmp_path / "feeder.onnx").write_bytes(b"x")
    built = build_detector("student", tmp_path / "models", load_species(), student_dir=tmp_path)
    assert built.name == "Feeder student 640"


# --- train_student: the parts that need no GPU ---


def test_yolo26_exports_end_to_end_and_yolo11_exports_with_nms():
    assert train_student.export_args("yolo26n.pt", 640) == dict(format="onnx", imgsz=640, nms=False, simplify=True)
    assert train_student.export_args("yolo11n.pt", 416) == dict(
        format="onnx", imgsz=416, nms=True, conf=0.05, simplify=True)


def test_output_shape_must_be_one_by_n_by_six():
    train_student.check_output_shape([1, 300, 6])
    for bad in ([1, 84, 8400], [1, 300, 7], [300, 6], ["batch", 300, 6], [1, "n", 6]):
        with pytest.raises(ValueError, match=r"\[1, N, 6\]"):
            train_student.check_output_shape(bad)


def make_dataset(tmp_path):
    root = tmp_path / "dataset"
    for split, stems in {"train": ["a_00000000", "a_00001000", "b_00000000"], "val": ["d_00000000", "d_00001000", "c_00002000"]}.items():
        (root / "images" / split).mkdir(parents=True)
        (root / "labels" / split).mkdir(parents=True)
        for stem in stems:
            (root / "images" / split / f"{stem}.jpg").write_bytes(b"")
    labels = root / "labels" / "train"
    (labels / "a_00000000.txt").write_text("0 0.5 0.5 0.1 0.1\n0 0.2 0.2 0.1 0.1\n2 0.8 0.8 0.1 0.1\n")
    (labels / "a_00001000.txt").write_text("1 0.5 0.5 0.1 0.1\n")
    (labels / "b_00000000.txt").write_text("")
    (root / "labels" / "val" / "d_00000000.txt").write_text("0 0.5 0.5 0.1 0.1\n")
    return root


def test_train_boxes_count_class_ids_in_the_training_labels_only(tmp_path):
    root = make_dataset(tmp_path)
    classes = ["great_tit", "blue_tit", "unidentified"]
    assert train_student.count_train_boxes(root, classes) == {"great_tit": 2, "blue_tit": 1, "unidentified": 1}


def test_held_out_footage_is_the_sorted_video_stems_of_the_val_images(tmp_path):
    assert train_student.held_out_footage(make_dataset(tmp_path)) == ["c", "d"]


def test_card_has_the_fields_the_detector_reads():
    card = train_student.build_card(
        base="yolo26n.pt", imgsz=640, classes=["great_tit", "unidentified"], train_boxes={"great_tit": 70, "unidentified": 0},
        held_out=["d"], trained_at="2026-11-14T10:00:00Z")
    assert card == {
        "name": "Feeder student 640", "kind": "student", "base": "yolo26n", "imgsz": 640,
        "classes": ["great_tit", "unidentified"], "count_threshold": 0.60, "trained_at": "2026-11-14T10:00:00Z",
        "train_boxes": {"great_tit": 70, "unidentified": 0}, "held_out_footage": ["d"], "metrics": None}


def test_train_student_imports_without_ultralytics():
    import sys

    assert "ultralytics" not in sys.modules and "torch" not in sys.modules
