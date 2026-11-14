"""Run the feeder census: python -m feeder_census --videos clip.mp4 --detector auto"""
import argparse
import json
import math
import signal
import sys
import threading
from pathlib import Path

import uvicorn

from feeder_census.camera import SimulatedCamera, _expand
from feeder_census.config import Settings
from feeder_census.detectors import KINDS, build_detector
from feeder_census.pipeline import LiveState, Pipeline
from feeder_census.species import load_species
from feeder_census.store import Store
from feeder_census.web import create_app


def _roi(text: str) -> tuple[float, float, float, float]:
    try:
        x, y, w, h = (float(v) for v in text.split(","))
    except ValueError:
        raise argparse.ArgumentTypeError("expected x,y,w,h as four fractions, e.g. 0.1,0.1,0.8,0.8")
    if not (0 <= x < 1 and 0 <= y < 1 and 0 < w <= 1 and 0 < h <= 1):
        raise argparse.ArgumentTypeError("roi fractions must lie inside the frame")
    return x, y, w, h


def _positive(text: str) -> float:
    value = float(text)
    if value <= 0:
        raise argparse.ArgumentTypeError("must be above 0")
    return value


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m feeder_census", description=__doc__)
    p.add_argument("--videos", nargs="+", required=True, type=Path, help="video files or folders")
    p.add_argument("--detector", choices=("auto", *KINDS), default="auto",
                   help="auto: the kind named by models/model_card.json, else two_stage (default: %(default)s)")
    p.add_argument("--db", type=Path, default=Path("data/census.db"))
    p.add_argument("--port", type=int, default=Settings.port)
    p.add_argument("--fast", action="store_true", help="play unpaced, to fill the table before a demo")
    p.add_argument("--no-web", action="store_true", help="print a line per detection instead of serving the page")
    p.add_argument("--detect-every-s", type=_positive, default=Settings.detect_every_s,
                   help="footage seconds between detections (default: %(default)s)")
    p.add_argument("--roi", type=_roi, default=None, help="x,y,w,h as fractions of the frame")
    p.add_argument("--script", type=Path, default=None, help="script file for --detector scripted")
    p.add_argument("--models-dir", type=Path, default=Path("models"))
    p.add_argument("--student-dir", type=Path, default=None)
    p.add_argument("--footage-note", default=None,
                   help="a line shown under the feed (default: says so when a clip has a .segments.csv beside it)")
    return p


EDITED_NOTE = "Edited to the busy parts of a longer recording."


def _footage_note(videos: list[Path]) -> str | None:
    """The edited-cut note when any clip has the `<clip>.segments.csv` that tools/mine_frames.py --highlights writes."""
    edited = any(Path(f"{clip}.segments.csv").is_file() for clip in _expand(videos))
    return EDITED_NOTE if edited else None


def _card_threshold(card: dict, path: Path) -> float | None:
    """The card's count_threshold: absent is None; anything but a finite number from 0 to 1 stops the run (exit 2)."""
    if "count_threshold" not in card:
        return None
    value = card["count_threshold"]
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
        print(f"error: {path}: count_threshold must be a number from 0 to 1, got {value!r}", file=sys.stderr)
        sys.exit(2)
    return float(value)


CARD_KINDS = ("student", "two_stage")


def resolve_detector(requested: str, models_dir: Path) -> tuple[str, dict | None]:
    """The detector kind to build and the model card to show with it.

    A card is only returned with the kind it was measured for: a card for another detector is dropped.
    A card that cannot be read, or names another kind, stops the run (exit 2).
    """
    path = Path(models_dir) / "model_card.json"
    card = None
    if path.is_file():
        try:
            card = json.loads(path.read_text())
        except (OSError, ValueError) as exc:
            print(f"error: cannot read {path}: {exc}", file=sys.stderr)
            sys.exit(2)
        if not isinstance(card, dict) or card.get("kind") not in CARD_KINDS:
            kind = card.get("kind") if isinstance(card, dict) else card
            print(f"error: {path}: kind must be one of {', '.join(CARD_KINDS)}, got {kind!r}", file=sys.stderr)
            sys.exit(2)
    if requested == "auto":
        return (card["kind"], card) if card else ("two_stage", None)
    return requested, card if card and card["kind"] == requested else None


def _print_line(state: LiveState) -> None:
    seen = {k: v for k, v in state.now.items() if v}
    confirmed = {k: v for k, v in state.confirmed.items() if v}
    print(f"{state.sim_time:%Y-%m-%d %H:%M:%S}  now={seen}  confirmed={confirmed}  detect_ms={state.detect_ms:.1f}", flush=True)


def _serve(app, port: int, stop: threading.Event) -> None:
    """Serve until Ctrl-C or SIGTERM. Open video streams end first, or the shutdown would wait on them."""

    class Server(uvicorn.Server):
        def handle_exit(self, sig, frame) -> None:
            stop.set()
            app.state.stopping.set()
            super().handle_exit(sig, frame)

    print(f"Feeder Census: http://localhost:{port}", flush=True)
    config = uvicorn.Config(app, host="0.0.0.0", port=port, access_log=False, timeout_graceful_shutdown=5)
    Server(config).run()


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    kind, card = resolve_detector(args.detector, args.models_dir)
    resolved_card = card
    if kind == "student" and args.student_dir:
        card = None  # the card describes models/student, not another folder
    species = load_species()
    names = {s.key: s.english for s in species}
    try:
        detector = build_detector(
            kind, args.models_dir, species, script=args.script, student_dir=args.student_dir
        )
        camera = SimulatedCamera(args.videos, realtime=not args.fast)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if card is not None and card.get("name") != detector.name:
        # stale files: the card was measured for another model than the one that loaded
        print(f"warning: model card is for {card.get('name')!r} but {detector.name!r} loaded; not showing the card",
              file=sys.stderr)
        card = None
    # the reason is decided after the guards above, which can drop the card
    ignored = resolved_card is not None and card is None
    if args.detector != "auto":
        why = "asked for, model card ignored" if ignored else "asked for"
    else:
        why = "model card ignored" if ignored else "model card" if card else "no model card"
    threshold = _card_threshold(card, args.models_dir / "model_card.json") if card else None
    args.db.parent.mkdir(parents=True, exist_ok=True)
    store = Store(args.db, detector.species)
    settings = Settings(
        detect_every_s=args.detect_every_s, roi=args.roi, port=args.port,
        evidence_dir=args.db.parent / "evidence", count_threshold=threshold,
        footage_note=args.footage_note if args.footage_note is not None else _footage_note(args.videos),
    )
    in_force = threshold if threshold is not None else detector.count_threshold
    print(f"detector: {kind} ({why}); counting threshold {in_force:g}", flush=True)
    pipeline = Pipeline(
        camera, detector, store, settings, names, inline=args.fast, on_result=_print_line if args.no_web else None
    )

    stop = threading.Event()
    failure: list[BaseException] = []

    def work() -> None:
        try:
            pipeline.run(stop)
        except Exception as exc:
            failure.append(exc)
            if pipeline.error is None:
                pipeline.error = exc  # the page shows it instead of looking alive

    # `kill` (SIGTERM) stops the run the same clean way as Ctrl-C
    signal.signal(signal.SIGTERM, lambda signum, frame: stop.set())
    thread = threading.Thread(target=work, name="pipeline")
    thread.start()
    try:
        if args.no_web:
            while thread.is_alive():
                thread.join(0.2)
        else:
            _serve(create_app(pipeline, store, species, settings, model_card=card), settings.port, stop)
    except KeyboardInterrupt:
        pass
    finally:  # also when uvicorn exits early, e.g. the port is taken
        stop.set()
        thread.join()
    if failure:
        print(f"error: {failure[0]}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
