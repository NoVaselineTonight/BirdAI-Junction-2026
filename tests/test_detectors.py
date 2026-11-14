from pathlib import Path

import numpy as np
import pytest

from feeder_census.detectors import build_detector
from feeder_census.detectors.base import letterbox, nms
from feeder_census.detectors.scripted import ScriptedDetector
from feeder_census.detectors.two_stage import TwoStageDetector
from feeder_census.detectors.yolox import decode_yolox
from feeder_census.species import load_species


@pytest.fixture
def species():
    return load_species()


class Fake:
    """Returns the given values in order; each keyword names a method."""

    def __init__(self, **calls):
        self._queues = {name: list(values) for name, values in calls.items()}

    def __getattr__(self, name):
        queue = self.__dict__["_queues"][name]
        return lambda *args, **kwargs: queue.pop(0)


def test_decode_yolox_maps_a_grid_cell_to_pixels():
    out = np.zeros((1, 3549, 85), np.float32)
    out[0, 0, :4] = [0.5, 0.5, np.log(4), np.log(2)]   # first cell of the stride-8 grid
    out[0, 0, 4] = 0.9; out[0, 0, 5 + 14] = 0.8
    boxes, scores = decode_yolox(out, size=416, class_id=14)
    assert boxes[0] == pytest.approx([-12, -4, 20, 12]) and scores[0] == pytest.approx(0.72)

def test_nms_keeps_one_box_per_bird():
    boxes = np.array([[0, 0, 100, 100], [5, 5, 105, 105], [200, 200, 260, 260]], np.float32)
    assert nms(boxes, np.array([0.9, 0.8, 0.7]), iou=0.45) == [0, 2]

def test_nms_drops_a_box_nested_inside_another():
    boxes = np.array([[0, 0, 100, 100], [30, 5, 70, 40], [90, 90, 190, 190]], np.float32)
    scores = np.array([0.9, 0.8, 0.7])
    assert nms(boxes, scores, iou=0.45) == [0, 1, 2]
    assert nms(boxes, scores, iou=0.45, contain=0.8) == [0, 2]
    assert nms(boxes, np.array([0.8, 0.9, 0.7]), iou=0.45, contain=0.8) == [1, 2]

def test_letterbox_round_trip():
    img = np.zeros((1080, 1920, 3), np.uint8)
    out, ratio, (dx, dy) = letterbox(img, 416, center=False)
    assert out.shape == (416, 416, 3) and ratio == pytest.approx(416 / 1920) and (dx, dy) == (0, 0)
    _, ratio_c, (dx, dy) = letterbox(img, 640, center=True)
    assert (dx, dy) == (0, 140) and ratio_c == pytest.approx(640 / 1920)

def test_two_stage_names_listed_species_and_flags_the_rest(species):
    boxes = Fake(boxes=[[((10, 10, 60, 60), 0.9), ((100, 100, 150, 150), 0.8)]])
    clf = Fake(classify=[("Parus major", 0.91), ("Poecile atricapillus", 0.80)])
    dets = TwoStageDetector(boxes, clf, species).detect(np.zeros((200, 200, 3), np.uint8))
    assert [(d.species, d.confidence) for d in dets] == [("great_tit", 0.91), ("unidentified", 0.80)]
    assert dets[0].box == (10, 10, 60, 60)

def test_two_stage_resolves_old_names_through_aliases(species):
    clf = Fake(classify=[("Carduelis spinus", 0.7)])
    (d,) = TwoStageDetector(Fake(boxes=[[((0, 0, 9, 9), 0.9)]]), clf, species).detect(np.zeros((20, 20, 3), np.uint8))
    assert d.species == "siskin"

def test_scripted_detector_cycles():
    d = ScriptedDetector({"species": ["great_tit"], "frames": [[], [{"species": "great_tit", "confidence": 0.9, "box": [0, 0, 5, 5]}]]})
    assert [len(d.detect(None)) for _ in range(3)] == [0, 1, 0]

def test_build_detector_rejects_unknown_kind_and_missing_files(species, tmp_path):
    with pytest.raises(ValueError, match="two_stage"):
        build_detector("nope", tmp_path, species)
    with pytest.raises(FileNotFoundError, match="fetch_models.py"):
        build_detector("two_stage", tmp_path, species)
    with pytest.raises(FileNotFoundError, match="feeder.onnx"):
        build_detector("student", tmp_path, species)
    (tmp_path / "student").mkdir()
    (tmp_path / "student" / "feeder.onnx").write_bytes(b"x")
    with pytest.raises(FileNotFoundError, match="feeder.json"):
        build_detector("student", tmp_path, species)

@pytest.mark.models
def test_pretrained_models_load_and_know_the_core_species(species):
    det = build_detector("two_stage", Path("models"), species)
    assert {s.key for s in species if s.core} <= set(det.species)
    assert det.detect(np.full((720, 1280, 3), 114, np.uint8)) == []
