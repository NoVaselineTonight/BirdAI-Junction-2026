import warnings
from datetime import datetime

import pytest

with warnings.catch_warnings():
    # starlette 1.x prefers `httpx2`; pyproject pins `httpx`, which still works
    warnings.filterwarnings("ignore", message="Using `httpx` with `starlette.testclient` is deprecated")
    from fastapi.testclient import TestClient

from feeder_census.camera import SimulatedCamera
from feeder_census.config import Settings
from feeder_census.detectors.scripted import ScriptedDetector
from feeder_census.pipeline import Pipeline
from feeder_census.species import load_species
from feeder_census.store import Store
from feeder_census.web import create_app

SPECIES = load_species()
NAMES = {s.key: s.english for s in SPECIES}
GT = {"species": "great_tit", "confidence": 0.9, "box": [10, 10, 60, 60]}


def scripted_app(tmp_path, make_video, detector_species, frames, detections):
    """A web app over a scripted pipeline that has run `detections` detections inline."""
    detector = ScriptedDetector({"species": detector_species, "frames": frames})
    store = Store(tmp_path / "census.db", detector.species)
    camera = SimulatedCamera([make_video(seconds=2.0, fps=10)], realtime=False)
    settings = Settings(evidence_dir=tmp_path / "evidence")
    pipeline = Pipeline(camera, detector, store, settings, NAMES, inline=True)
    calls = 0
    original = detector.detect

    def counting(frame):
        nonlocal calls
        calls += 1
        return original(frame)

    detector.detect = counting
    for _ in range(10_000):
        if calls >= detections:
            break
        pipeline.step()
    assert calls >= detections, "pipeline never ran the detections"
    return create_app(pipeline, store, SPECIES, settings, model_card=None), store, pipeline


@pytest.fixture
def web(tmp_path, make_video):
    return scripted_app(tmp_path, make_video, ["great_tit", "blue_tit"], [[GT, GT]], 3)


@pytest.fixture
def client(web):
    with TestClient(web[0]) as c:
        yield c


@pytest.fixture
def store(web):
    return web[1]


def test_live_state_has_the_fields_the_page_needs(client):
    j = client.get("/api/live").json()
    assert j["recorded"] is True and j["time_scale"] == 60 and j["confirmed"]["great_tit"] == 2
    assert set(j) >= {"sim_time", "detector", "detect_ms", "now", "confirmed", "unidentified"}
    assert j["error"] is None and j["detector"] == "scripted"


def test_tables_match_the_store(client, store):
    j = client.get("/api/tables").json()
    assert j["periods"][0]["label"] == "1–15 November 2026"
    assert j["periods"][0]["counts"]["great_tit"] == store.periods()[0].counts["great_tit"] == 2
    assert [r["key"] for r in j["hours"]] == ["08"] and [r["key"] for r in j["days"]] == ["2026-11-01"]


def test_tables_hide_species_the_detector_cannot_name(client):
    keys = [s["key"] for s in client.get("/api/tables").json()["species"]]
    assert keys == ["great_tit", "blue_tit"]          # the scripted detector's list; no yellowhammer column of zeros


def test_non_core_species_gets_a_column_only_when_seen(tmp_path, make_video):
    app, store, _ = scripted_app(tmp_path, make_video, ["great_tit", "magpie"], [[GT]], 2)
    with TestClient(app) as c:
        assert [s["key"] for s in c.get("/api/tables").json()["species"]] == ["great_tit"]
        store.record(datetime(2026, 11, 1, 9, 0), {"magpie": 1}, 60)
        species = c.get("/api/tables").json()["species"]
    assert [s["key"] for s in species] == ["great_tit", "magpie"]
    assert species[1] == {"key": "magpie", "english": "Magpie", "finnish": "Harakka", "habitat": "town"}


def test_habitat_mix_covers_only_nameable_species(client):
    h = {x["key"]: x for x in client.get("/api/tables").json()["habitats"]}
    assert h["generalist"]["birds"] == 2 and h["generalist"]["species"] == ["Great tit", "Blue tit"]
    assert h["forest"] == {"key": "forest", "label": "Forest birds", "birds": 0, "species": []}


def test_csv_download(client):
    r = client.get("/export/census.csv")
    assert r.headers["content-disposition"].endswith('filename="feeder-census.csv"')
    assert r.headers["content-type"] == "text/csv; charset=utf-8"
    assert r.text.splitlines()[0].startswith("Period,Hours watched,Great tit")


def test_evidence_photo_is_served_and_paths_cannot_escape(client):
    assert client.get("/evidence/2026-11-01/great_tit.jpg").headers["content-type"] == "image/jpeg"
    assert client.get("/evidence/2026-11-01/blue_tit.jpg").status_code == 404
    assert client.get("/evidence/..%2F..%2Fcensus.db/x.jpg").status_code == 404


def test_evidence_list_links_the_photos(client):
    (e,) = client.get("/api/evidence").json()
    assert (e["day"], e["species"], e["count"]) == ("2026-11-01", "great_tit", 2)
    assert e["url"] == "/evidence/2026-11-01/great_tit.jpg" and client.get(e["url"]).status_code == 200


def test_model_without_a_card_names_the_detector(client):
    assert client.get("/api/model").json() == {"name": "scripted", "metrics": None}


def test_page_carries_the_honesty_lines(client):
    html = client.get("/").text
    assert "Recorded feeder footage, standing in for the camera." in html
    assert "Largest number seen at once. Only surely identified birds are counted." in html
    assert "Our own grouping, not yet checked against Luomus." in html


def test_stream_sends_the_preview_and_ends_when_the_server_stops(web, client):
    web[0].state.stopping.set()
    r = client.get("/stream.mjpg")
    assert r.headers["content-type"] == "multipart/x-mixed-replace; boundary=frame"
    assert r.content.startswith(b"--frame\r\nContent-Type: image/jpeg\r\n") and b"\xff\xd8" in r.content



def test_live_state_reports_a_stopped_pipeline(web, client):
    assert client.get("/api/live").json()["error"] is None
    web[2].error = RuntimeError("camera lost")
    assert client.get("/api/live").json()["error"] == "camera lost"
