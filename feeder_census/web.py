"""The demo page: live feed, counts, evidence photos and CSV export, served by the pipeline's process."""
import asyncio
import io
import re
import threading
from collections.abc import AsyncIterator, Sequence
from dataclasses import asdict
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from feeder_census.config import Settings
from feeder_census.periods import period_of
from feeder_census.pipeline import Pipeline
from feeder_census.species import HABITATS, Species, habitat_mix
from feeder_census.store import Store

STATIC = Path(__file__).resolve().parent / "static"
HABITAT_LABELS = {
    "forest": "Forest birds", "farmland": "Farmland birds", "town": "Town birds", "generalist": "Generalists",
}
_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")
_BOUNDARY = "frame"


def create_app(
    pipeline: Pipeline, store: Store, species: Sequence[Species], settings: Settings, model_card: dict | None,
) -> FastAPI:
    """The page and its API. Set `app.state.stopping` to end open MJPEG streams before the server shuts down."""
    app = FastAPI(title="Feeder Census", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.stopping = threading.Event()
    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    nameable = [s for s in species if s.key in pipeline.detector.species]  # species.toml order
    english = {s.key: s.english for s in species}

    @app.get("/", include_in_schema=False)
    def page() -> FileResponse:
        return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})

    @app.get("/api/live")
    def live() -> dict:
        s = pipeline.live()
        error = pipeline.error
        return {
            "sim_time": s.sim_time.isoformat(), "detector": s.detector, "detect_ms": round(s.detect_ms, 1),
            "now": s.now, "confirmed": s.confirmed, "unidentified": s.unidentified,
            "day_max": s.day_max, "visits_today": s.visits_today,  # visits are arrivals, not birds
            "time_scale": settings.time_scale, "recorded": True,
            "error": None if error is None else (str(error) or type(error).__name__),
        }

    @app.get("/api/tables")
    def tables() -> dict:
        today = pipeline.live().sim_time.date()
        period = period_of(today)
        hours, days, periods = store.hours(today), store.days(period), store.periods()
        seen = {k for row in (*hours, *days, *periods) for k, n in row.counts.items() if n > 0}
        visible = [s for s in nameable if s.core or s.key in seen]
        current = next((r.counts for r in periods if r.key == period.key), {})
        mix = habitat_mix(current, nameable)
        return {
            "species": [{"key": s.key, "english": s.english, "finnish": s.finnish, "habitat": s.habitat}
                        for s in visible],
            "nameable": [{"key": s.key, "english": s.english, "finnish": s.finnish} for s in nameable],
            "day": today.isoformat(),
            "period": period.label,
            "hours": [asdict(r) for r in hours],
            "days": [asdict(r) for r in days],
            "periods": [asdict(r) for r in periods],
            "habitats": [{"key": h, "label": HABITAT_LABELS[h], "birds": mix[h],
                          "species": [s.english for s in nameable if s.habitat == h]} for h in HABITATS],
        }

    @app.get("/api/evidence")
    def evidence() -> list[dict]:
        return [{"day": e.day.isoformat(), "species": e.species, "count": e.count,
                 "confidence": round(e.confidence, 3), "ts": e.ts.isoformat(),
                 "url": f"/evidence/{e.day.isoformat()}/{e.species}.jpg"} for e in store.evidence()]

    @app.get("/evidence/{day}/{species}.jpg")
    def evidence_photo(day: str, species: str) -> FileResponse:
        if not _DAY.fullmatch(day) or species not in store.species:
            raise HTTPException(404)
        try:
            date.fromisoformat(day)
        except ValueError:
            raise HTTPException(404)
        path = settings.evidence_dir / day / f"{species}.jpg"
        if not path.is_file():
            raise HTTPException(404)
        return FileResponse(path, media_type="image/jpeg")

    @app.get("/export/census.csv")
    def export() -> Response:
        out = io.StringIO(newline="")
        store.export_csv(out, english)
        return Response(out.getvalue(), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": 'attachment; filename="feeder-census.csv"'})

    @app.get("/api/model")
    def model() -> dict:
        return model_card if model_card is not None else {"name": pipeline.detector.name, "metrics": None}

    @app.get("/stream.mjpg")
    async def stream(request: Request) -> StreamingResponse:
        return StreamingResponse(
            _frames(pipeline, request, app.state.stopping, settings.preview_fps),
            media_type=f"multipart/x-mixed-replace; boundary={_BOUNDARY}",
            headers={"Cache-Control": "no-store"},
        )

    return app


async def _frames(pipeline: Pipeline, request: Request, stopping: threading.Event, fps: float) -> AsyncIterator[bytes]:
    """The latest preview JPEG whenever it changed, until the client leaves or the server stops."""
    last = b""
    while True:
        jpeg = pipeline.live().jpeg
        if jpeg and jpeg is not last:
            last = jpeg
            yield (f"--{_BOUNDARY}\r\nContent-Type: image/jpeg\r\nContent-Length: {len(jpeg)}\r\n\r\n".encode()
                   + jpeg + b"\r\n")
        if stopping.is_set() or await request.is_disconnected():
            return
        await asyncio.sleep(1.0 / fps)
