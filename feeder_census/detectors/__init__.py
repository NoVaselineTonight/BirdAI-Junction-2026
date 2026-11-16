from collections.abc import Sequence
from pathlib import Path

from feeder_census.detectors.base import Detector
from feeder_census.species import Species

KINDS = ("two_stage", "student", "scripted")

__all__ = ["Detector", "KINDS", "build_detector"]


def _require(path: Path, hint: str) -> Path:
    if not path.is_file():
        raise FileNotFoundError(f"missing model file {path}; {hint}")
    return path


def build_detector(
    kind: str,
    models_dir: Path,
    species: Sequence[Species],
    script: Path | None = None,
    student_dir: Path | None = None,
) -> Detector:
    models_dir = Path(models_dir)
    if kind == "two_stage":
        from feeder_census.detectors.inat import InatClassifier
        from feeder_census.detectors.two_stage import TwoStageDetector
        from feeder_census.detectors.yolox import YoloxBoxes

        pretrained = models_dir / "pretrained"
        hint = "run: python tools/fetch_models.py"
        yolox = _require(pretrained / "yolox_nano.onnx", hint)
        tflite = _require(pretrained / "inat_bird.tflite", hint)
        labels = _require(pretrained / "inat_bird_labels.txt", hint)
        classifier = InatClassifier(tflite, labels)
        known = set(classifier.labels)
        in_labels = [s for s in species if known & {s.scientific, *s.aliases}]
        return TwoStageDetector(YoloxBoxes(yolox), classifier, in_labels)
    if kind == "student":
        student_dir = Path(student_dir) if student_dir else models_dir / "student"
        hint = "train the student model first"
        model = _require(student_dir / "feeder.onnx", hint)
        card = _require(student_dir / "feeder.json", hint)
        from feeder_census.detectors.student import StudentDetector

        return StudentDetector(model, card)
    if kind == "scripted":
        if script is None:
            raise ValueError("the scripted detector needs a script file")
        from feeder_census.detectors.scripted import ScriptedDetector

        return ScriptedDetector(script)
    raise ValueError(f"unknown detector kind {kind!r}; valid kinds: {', '.join(KINDS)}")
