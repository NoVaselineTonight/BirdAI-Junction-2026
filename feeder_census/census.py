from collections import Counter, deque
from collections.abc import Iterable, Mapping, Sequence

from .types import UNIDENTIFIED, Detection


def frame_counts(detections: Iterable[Detection], threshold: float) -> dict[str, int]:
    """Birds per species in one frame, counting only surely identified ones."""
    counts = Counter(
        d.species
        for d in detections
        if d.species != UNIDENTIFIED and d.confidence >= threshold
    )
    return dict(counts)


class ConfirmFilter:
    """Per species, the minimum count over the last `confirm_frames` frames.

    A species counts only when it was seen in every one of those frames, so a
    single-frame spike never reaches the census.
    """

    def __init__(self, species: Sequence[str], confirm_frames: int = 2) -> None:
        self._species = list(species)
        self._confirm_frames = confirm_frames
        self._history: deque[dict[str, int]] = deque(maxlen=confirm_frames)

    def update(self, counts: Mapping[str, int]) -> dict[str, int]:
        self._history.append({s: counts.get(s, 0) for s in self._species})
        if len(self._history) < self._confirm_frames:
            return {s: 0 for s in self._species}
        return {s: min(frame[s] for frame in self._history) for s in self._species}

    def reset(self) -> None:
        self._history.clear()
