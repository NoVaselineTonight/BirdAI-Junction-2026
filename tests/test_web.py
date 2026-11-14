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


def scripted_app(tmp_path, make_video, detector_species, frames, detections, model_card=None, **settings):
    """A web app over a scripted pipeline that has run `detections` detections inline."""
    detector = ScriptedDetector({"species": detector_species, "frames": frames})
    tmp_path.mkdir(parents=True, exist_ok=True)
    store = Store(tmp_path / "census.db", detector.species)
    camera = SimulatedCamera([make_video(seconds=2.0, fps=10)], realtime=False)
    settings = Settings(evidence_dir=tmp_path / "evidence", **settings)
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
    return create_app(pipeline, store, SPECIES, settings, model_card=model_card), store, pipeline


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


def test_live_state_carries_visits_and_day_maximum(client):
    j = client.get("/api/live").json()
    assert j["visits_today"]["great_tit"] >= 1 and j["day_max"]["great_tit"] == 2
    assert set(j["visits_today"]) == set(j["now"])
    assert set(j["day_max"]) == set(j["now"])


def test_page_says_what_a_visit_is(client):
    assert "Visits are arrivals at the feeder, not individual birds. The camera cannot tell one bird from another." in client.get("/").text


def test_visits_stay_out_of_the_census_csv(client):
    assert "visit" not in client.get("/export/census.csv").text.lower()


def test_tables_name_every_species_the_model_can_name_with_its_key(client):
    nameable = client.get("/api/tables").json()["nameable"]
    assert nameable[0] == {"key": "great_tit", "english": "Great tit", "finnish": "Talitiainen"}


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
    assert r.content.startswith(b"\xef\xbb\xbf")  # a UTF-8 byte-order mark, so Excel reads the en dash right
    assert r.content[3:].decode("utf-8").splitlines()[0].startswith("Period,Hours watched,Great tit")


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


def test_model_card_is_passed_through_with_unmeasured_rates(tmp_path, make_video):
    card = {
        "name": "Feeder student 640", "count_threshold": 0.6,
        "threshold_source": "default: too few validation boxes to pick", "board_ms": 412,
        "metrics": {"count_exact": None, "per_species": {
            "great_tit": {"precision": 0.94, "recall": 0.71, "val_boxes": 132},
            "blue_tit": {"precision": None, "recall": None, "val_boxes": 0}}},
    }
    app, _, _ = scripted_app(tmp_path, make_video, ["great_tit", "blue_tit"], [[GT]], 1, model_card=card)
    with TestClient(app) as c:
        assert c.get("/api/model").json() == card


def test_live_state_carries_the_footage_note(tmp_path, make_video, client):
    assert client.get("/api/live").json()["footage_note"] is None
    app, _, _ = scripted_app(tmp_path / "edited", make_video, ["great_tit"], [[GT]], 1,
                             footage_note="Edited to the busy parts of a longer recording.")
    with TestClient(app) as c:
        assert c.get("/api/live").json()["footage_note"] == "Edited to the busy parts of a longer recording."


def test_live_state_says_the_photo_interval_in_photo_mode_and_null_otherwise(tmp_path, make_video, client):
    assert client.get("/api/live").json()["photo_every_s"] is None
    app, _, _ = scripted_app(tmp_path / "photo", make_video, ["great_tit"], [[GT]], 1, photo_mode=True, detect_every_s=5.0)
    with TestClient(app) as c:
        assert c.get("/api/live").json()["photo_every_s"] == 5


def test_page_has_a_place_for_the_photo_note_and_the_script_words_it(client):
    assert 'id="photo-note"' in client.get("/").text
    js = client.get("/static/app.js").text
    assert "One photo every ${" in js and "s, as the board's camera would take them." in js


def test_script_says_when_the_model_card_is_below_the_accuracy_bar_and_only_for_an_exact_false(client):
    js = client.get("/static/app.js").text
    assert "Below our accuracy bar; it ships because it counts better than the alternative." in js
    assert 'modelCard.kind === "student" && m.qualified === false' in js


def test_page_has_a_place_for_the_footage_note_after_the_recorded_line(client):
    html = client.get("/").text
    assert html.index("Recorded feeder footage, standing in for the camera.") < html.index('id="footage-note"')


def test_static_files_are_revalidated_and_not_versioned_by_hand(client):
    assert client.get("/static/app.js").headers["cache-control"] == "no-cache"
    assert client.get("/static/style.css").headers["cache-control"] == "no-cache"
    assert "?v=" not in client.get("/").text


def test_evidence_photo_rejects_a_bad_date_and_an_unknown_species(client):
    assert client.get("/evidence/2026-13-45/great_tit.jpg").status_code == 404
    assert client.get("/evidence/2026-11-01/dodo.jpg").status_code == 404


def test_evidence_photo_does_not_follow_a_symlinked_day_out_of_the_evidence_dir(tmp_path, client):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "great_tit.jpg").write_bytes(b"\xff\xd8 not evidence")
    (tmp_path / "evidence" / "2026-11-02").symlink_to(outside, target_is_directory=True)
    assert client.get("/evidence/2026-11-02/great_tit.jpg").status_code == 404


SQ = {"species": "red_squirrel", "confidence": 0.9, "box": [100, 100, 200, 200]}


def test_live_state_carries_the_latch(tmp_path, make_video, client):
    j = client.get("/api/live").json()
    assert j["latch"] == {"mode": "off", "closed": False, "reason": None, "error": None, "reason_name": None,
                          "headline": "off"}
    assert j["pests"] == {"red_squirrel": 0, "brown_rat": 0}
    app, _, _ = scripted_app(tmp_path / "squirrel", make_video, ["great_tit"], [[GT, SQ]], 3, latch="sim")
    with TestClient(app) as c:
        j = c.get("/api/live").json()
        assert j["latch"] == {"mode": "sim", "closed": True, "reason": "red_squirrel", "error": None,
                              "reason_name": {"english": "Red squirrel", "finnish": "Orava"}, "headline": "closed"}
        assert j["pests"] == {"red_squirrel": 1, "brown_rat": 0}
        assert j["unidentified"] == 0 and "red_squirrel" not in j["now"]
        tables = c.get("/api/tables").json()
        assert "red_squirrel" not in {s["key"] for s in tables["species"] + tables["nameable"]}
        assert "squirrel" not in c.get("/export/census.csv").text.lower()


def test_page_says_what_the_latch_does(client):
    html = client.get("/").text
    assert "The latch closes when a squirrel is at the feeder. This model has not learned rats yet." in html
    assert "Latch not connected: showing what it would do." in html
    assert "Latch not answering:" in html
    assert 'id="latch" hidden' in html


def router_app(tmp_path, make_video, frames, detections, fail):
    """A web app over a scripted pipeline whose latch answers or raises as `fail` says, call by call."""
    from feeder_census.latch import LatchError

    class Board:
        def __init__(self):
            self.answers = list(fail)

        def set(self, closed):
            message = self.answers.pop(0) if self.answers else None
            if message is not None:
                raise LatchError(message)

    detector = ScriptedDetector({"species": ["great_tit"], "frames": frames})
    store = Store(tmp_path / "census.db", detector.species)
    camera = SimulatedCamera([make_video(seconds=2.0, fps=10)], realtime=False)
    settings = Settings(evidence_dir=tmp_path / "evidence", latch="router", latch_close_frames=1,
                        latch_open_frames=1)
    pipeline = Pipeline(camera, detector, store, settings, NAMES, inline=True, latch=Board())
    n = 0
    original = detector.detect

    def counting(frame):
        nonlocal n
        n += 1
        return original(frame)

    detector.detect = counting
    while n < detections:
        pipeline.step()
    return create_app(pipeline, store, SPECIES, settings, model_card=None)


@pytest.mark.parametrize("frames, detections, fail, headline, closed, error", [
    ([[GT]], 1, [], "open", False, None),                                   # router, answering, open
    ([[GT, SQ]], 1, [], "closed", True, None),                              # router, answering, closed
    ([[GT, SQ]], 1, [None, "timed out"], "not_answering", True, "timed out"),  # closed, close not confirmed
    ([[GT, SQ], [GT]], 2, [None, None, "timed out"], "not_answering", False, "timed out"),  # open not confirmed
    ([[GT]], 0, ["no router socket"], "not_answering", False, "no router socket"),  # nothing at start-up
])
def test_live_latch_headline_follows_what_the_board_confirmed(
        tmp_path, make_video, frames, detections, fail, headline, closed, error):
    app = router_app(tmp_path, make_video, frames, detections, fail)
    with TestClient(app) as c:
        latch = c.get("/api/live").json()["latch"]
    assert (latch["headline"], latch["closed"], latch["error"]) == (headline, closed, error)


def test_page_draws_the_latch_from_the_headline_key(client):
    js = client.get("/static/app.js").text
    for key in ("off", "open", "closed", "not_answering"):
        assert f"{key}:" in js or f'"{key}"' in js
    assert "Latch: not answering" in js


def test_model_table_names_every_nameable_species_and_falls_back_to_a_readable_key(client):
    js = client.get("/static/app.js").text
    assert "tables.nameable" in js.split("function renderModel()")[1].split("/* ---------- feed")[0]
    assert "tables.species" not in js.split("function renderModel()")[1].split("/* ---------- feed")[0]
    assert 'k.replace(/_/g, " ")' in js
