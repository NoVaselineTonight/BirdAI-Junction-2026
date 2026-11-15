from dataclasses import dataclass
from datetime import date
from pathlib import Path


@dataclass
class Settings:
    time_scale: float = 60.0  # simulated seconds per second of footage
    detect_every_s: float = 2.0  # footage seconds between detections
    max_gap_s: float = 10.0  # most footage seconds one detection may credit
    confirm_frames: int = 2
    visit_gap_frames: int = 3  # detections a species must be gone before its return is a new visit
    count_threshold: float | None = None  # None = use the detector's
    roi: tuple[float, float, float, float] | None = None  # x, y, w, h as fractions of the frame
    sim_start: date = date(2026, 11, 1)
    evidence_dir: Path = Path("data/evidence")
    source: str = "recorded"  # "recorded" (video files) | "camera" (a live USB webcam)
    photo_mode: bool = False  # the analysed photos, each held until the next one, shown next to the live picture
    preview_fps: float = 5.0
    preview_width: int = 960
    port: int = 8088
    footage_note: str | None = None  # said under the feed, e.g. that the clip is an edited cut
    latch: str = "off"  # "off" | "sim" (no hardware, shows what it would do) | "router" (the servo on the board)
    latch_close_frames: int = 2  # detections in a row with a pest before the latch closes
    latch_open_frames: int = 5  # detections in a row without one before it opens again
    pest_threshold: float = 0.5  # minimum confidence for a pest box to count
