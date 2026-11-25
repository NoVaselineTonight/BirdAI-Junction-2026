from dataclasses import dataclass

UNIDENTIFIED = "unidentified"


@dataclass(frozen=True)
class Detection:
    """One bird found in a frame. `box` is x1, y1, x2, y2 in source-frame pixels."""

    species: str
    confidence: float
    box: tuple[float, float, float, float]
