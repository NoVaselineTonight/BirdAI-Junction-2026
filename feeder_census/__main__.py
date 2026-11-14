"""Run the feeder census: python -m feeder_census --videos clip.mp4 --detector two_stage"""
import argparse
import signal
import sys
import threading
from pathlib import Path

import uvicorn

from feeder_census.camera import SimulatedCamera
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
    p.add_argument("--detector", choices=KINDS, default="two_stage")
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
    return p


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
    species = load_species()
    names = {s.key: s.english for s in species}
    try:
        detector = build_detector(
            args.detector, args.models_dir, species, script=args.script, student_dir=args.student_dir
        )
        camera = SimulatedCamera(args.videos, realtime=not args.fast)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    args.db.parent.mkdir(parents=True, exist_ok=True)
    store = Store(args.db, detector.species)
    settings = Settings(detect_every_s=args.detect_every_s, roi=args.roi, port=args.port, evidence_dir=args.db.parent / "evidence")
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
            _serve(create_app(pipeline, store, species, settings, model_card=None), settings.port, stop)
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
