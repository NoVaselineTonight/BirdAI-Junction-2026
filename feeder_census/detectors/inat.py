from pathlib import Path

import cv2
import numpy as np
from ai_edge_litert.interpreter import Interpreter

BACKGROUND = "background"


class InatClassifier:
    """iNaturalist bird classifier (TFLite, uint8 in and out) naming a crop by scientific name."""

    def __init__(self, model: Path, labels: Path):
        lines = Path(labels).read_text(encoding="utf-8").splitlines()
        # "Scientific name (Common name)"; the last line is just "background"
        self.labels = [line.split(" (")[0].strip() for line in lines if line.strip()]
        self._interpreter = Interpreter(model_path=str(model), num_threads=4)
        self._interpreter.allocate_tensors()
        self._input = self._interpreter.get_input_details()[0]
        self._output = self._interpreter.get_output_details()[0]
        self._size = int(self._input["shape"][1])

    def classify(self, crop_bgr: np.ndarray) -> tuple[str, float]:
        rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
        rgb = cv2.resize(rgb, (self._size, self._size), interpolation=cv2.INTER_AREA)
        self._interpreter.set_tensor(self._input["index"], rgb[None].astype(np.uint8))
        self._interpreter.invoke()
        scores = self._interpreter.get_tensor(self._output["index"])[0]
        top = int(np.argmax(scores))
        return self.labels[top], float(scores[top]) / 256.0
