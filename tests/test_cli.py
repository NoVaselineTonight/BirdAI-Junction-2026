import pytest

from feeder_census import __main__ as cli
from feeder_census.config import Settings


def run_cli(monkeypatch, tmp_path, make_video, *extra):
    """Runs main() up to the Pipeline and returns the Settings it was given."""
    seen = {}

    class StubPipeline:
        error = None

        def __init__(self, camera, detector, store, settings, *args, **kwargs):
            seen["settings"] = settings

        def run(self, stop):
            pass

    monkeypatch.setattr(cli, "Pipeline", StubPipeline)
    script = tmp_path / "script.json"
    script.write_text('{"species": ["great_tit"], "frames": [[]]}')
    video = make_video()
    argv = ["--videos", str(video), "--detector", "scripted", "--script", str(script),
            "--db", str(tmp_path / "data" / "c.db"), "--no-web", *extra]
    assert cli.main(argv) == 0
    return seen["settings"]


def test_detect_every_s_defaults_to_the_settings_default(monkeypatch, tmp_path, make_video):
    settings = run_cli(monkeypatch, tmp_path, make_video)
    assert settings.detect_every_s == Settings.detect_every_s


def test_detect_every_s_flag_sets_the_detection_interval(monkeypatch, tmp_path, make_video):
    settings = run_cli(monkeypatch, tmp_path, make_video, "--detect-every-s", "4")
    assert settings.detect_every_s == 4.0


def test_detect_every_s_must_be_positive():
    with pytest.raises(SystemExit):
        cli._parser().parse_args(["--videos", "x.mp4", "--detect-every-s", "0"])


# --- photo mode ---


def test_photo_every_s_sets_photo_mode_and_the_interval(monkeypatch, tmp_path, make_video):
    settings = run_cli(monkeypatch, tmp_path, make_video, "--photo-every-s", "5")
    assert settings.photo_mode is True and settings.detect_every_s == 5.0 and settings.max_gap_s == 10.0


def test_photo_every_s_lets_a_whole_interval_count(monkeypatch, tmp_path, make_video):
    assert run_cli(monkeypatch, tmp_path, make_video, "--photo-every-s", "10").max_gap_s == 20.0
    assert run_cli(monkeypatch, tmp_path, make_video, "--photo-every-s", "2.5").max_gap_s == Settings.max_gap_s


def test_without_photo_every_s_nothing_changes(monkeypatch, tmp_path, make_video):
    settings = run_cli(monkeypatch, tmp_path, make_video)
    assert settings.photo_mode is False and settings.max_gap_s == Settings.max_gap_s


def test_photo_every_s_with_detect_every_s_is_a_usage_error(tmp_path, make_video, capsys):
    argv = ["--videos", str(make_video()), "--detector", "scripted", "--db", str(tmp_path / "c.db"),
            "--photo-every-s", "5", "--detect-every-s", "2"]
    with pytest.raises(SystemExit) as stop:
        cli.main(argv)
    assert stop.value.code == 2
    err = capsys.readouterr().err
    assert "--photo-every-s" in err and "--detect-every-s" in err and "one of" in err


def test_photo_every_s_must_be_positive():
    with pytest.raises(SystemExit):
        cli._parser().parse_args(["--videos", "x.mp4", "--photo-every-s", "0"])


# --- model card and --detector auto ---

import json  # noqa: E402


def write_card(models_dir, **fields):
    models_dir.mkdir(parents=True, exist_ok=True)
    card = {"name": "m", "kind": "student", "species": ["great_tit"], "count_threshold": 0.7, **fields}
    (models_dir / "model_card.json").write_text(json.dumps(card))
    return card


def test_auto_follows_the_card(tmp_path):
    card = write_card(tmp_path, kind="student")
    assert cli.resolve_detector("auto", tmp_path) == ("student", card)
    card = write_card(tmp_path, kind="two_stage")
    assert cli.resolve_detector("auto", tmp_path) == ("two_stage", card)


def test_auto_without_a_card_is_two_stage(tmp_path):
    assert cli.resolve_detector("auto", tmp_path) == ("two_stage", None)
    assert cli.resolve_detector("auto", tmp_path / "missing") == ("two_stage", None)


def test_explicit_kind_keeps_a_matching_card(tmp_path):
    card = write_card(tmp_path, kind="student")
    assert cli.resolve_detector("student", tmp_path) == ("student", card)


def test_explicit_kind_drops_a_card_measured_for_another_detector(tmp_path):
    write_card(tmp_path, kind="student")
    assert cli.resolve_detector("two_stage", tmp_path) == ("two_stage", None)
    assert cli.resolve_detector("scripted", tmp_path) == ("scripted", None)


def test_explicit_kind_without_a_card(tmp_path):
    assert cli.resolve_detector("student", tmp_path) == ("student", None)


def test_a_card_that_is_not_json_exits_2_naming_the_file(tmp_path, capsys):
    tmp_path.joinpath("model_card.json").write_text("{not json")
    with pytest.raises(SystemExit) as stop:
        cli.resolve_detector("auto", tmp_path)
    assert stop.value.code == 2
    assert str(tmp_path / "model_card.json") in capsys.readouterr().err


@pytest.mark.parametrize("body", ['{"kind": "scripted"}', '{"name": "x"}', '[1, 2]', '"student"'])
def test_a_card_with_an_unknown_kind_exits_2_naming_the_file(tmp_path, capsys, body):
    tmp_path.joinpath("model_card.json").write_text(body)
    with pytest.raises(SystemExit) as stop:
        cli.resolve_detector("auto", tmp_path)
    assert stop.value.code == 2
    assert str(tmp_path / "model_card.json") in capsys.readouterr().err


class StubDetector:
    name = "stub model"
    species = ("great_tit",)
    count_threshold = 0.60


def run_auto(monkeypatch, tmp_path, make_video, card, *extra, detector=StubDetector):
    """Runs main() with --detector auto over a models dir holding `card`; returns (settings, card given to the page)."""
    seen = {}

    class StubPipeline:
        error = None

        def __init__(self, camera, detector, store, settings, *args, **kwargs):
            seen["settings"] = settings

        def run(self, stop):
            pass

    def fake_app(pipeline, store, species, settings, model_card):
        seen["card"] = model_card

    models = tmp_path / "models"
    if card is not None:
        write_card(models, **card)
    built = {}
    monkeypatch.setattr(cli, "Pipeline", StubPipeline)
    monkeypatch.setattr(cli, "create_app", fake_app)
    monkeypatch.setattr(cli, "_serve", lambda *a, **k: None)
    monkeypatch.setattr(cli, "build_detector", lambda kind, *a, **k: built.setdefault("kind", kind) and detector())
    argv = ["--videos", str(make_video()), "--models-dir", str(models), "--db", str(tmp_path / "data" / "c.db"), *extra]
    assert cli.main(argv) == 0
    return seen["settings"], seen.get("card"), built["kind"]


def test_the_cards_count_threshold_reaches_the_settings(monkeypatch, tmp_path, make_video, capsys):
    settings, card, kind = run_auto(
        monkeypatch, tmp_path, make_video, {"kind": "two_stage", "name": "stub model", "count_threshold": 0.75})
    assert kind == "two_stage"
    assert settings.count_threshold == 0.75
    assert card["name"] == "stub model"
    out = capsys.readouterr().out
    assert "two_stage" in out and "model card" in out and "0.75" in out


def test_without_a_card_the_detectors_own_threshold_stays(monkeypatch, tmp_path, make_video, capsys):
    settings, card, kind = run_auto(monkeypatch, tmp_path, make_video, None)
    assert (kind, settings.count_threshold, card) == ("two_stage", None, None)
    out = capsys.readouterr().out
    assert "no model card" in out and "0.6" in out


def test_a_card_for_a_different_model_is_not_shown_or_used(monkeypatch, tmp_path, make_video, capsys):
    # stale files: the card names another model than the one that loaded
    settings, card, _ = run_auto(
        monkeypatch, tmp_path, make_video, {"kind": "student", "name": "older student", "count_threshold": 0.9})
    assert card is None and settings.count_threshold is None
    assert "older student" in capsys.readouterr().err


def test_a_custom_student_dir_never_shows_the_card(monkeypatch, tmp_path, make_video):
    settings, card, _ = run_auto(
        monkeypatch, tmp_path, make_video, {"kind": "student", "name": "stub model"}, "--student-dir", str(tmp_path))
    assert card is None and settings.count_threshold is None


# --- footage note ---

EDITED = "Edited to the busy parts of a longer recording."


def test_a_segments_file_beside_the_clip_sets_the_footage_note(monkeypatch, tmp_path, make_video):
    make_video()  # a.mp4, the clip run_cli plays
    (tmp_path / "a.mp4.segments.csv").write_text("start_s,end_s\n0,2\n")
    assert run_cli(monkeypatch, tmp_path, make_video).footage_note == EDITED


def test_a_segments_file_in_a_videos_folder_sets_the_footage_note(monkeypatch, tmp_path, make_video):
    make_video("clips/a.mp4")
    (tmp_path / "clips" / "a.mp4.segments.csv").write_text("start_s,end_s\n0,2\n")
    assert run_cli(monkeypatch, tmp_path, make_video, "--videos", str(tmp_path / "clips")).footage_note == EDITED


def test_footage_note_flag_wins_and_no_file_means_no_note(monkeypatch, tmp_path, make_video):
    assert run_cli(monkeypatch, tmp_path, make_video).footage_note is None
    (tmp_path / "a.mp4.segments.csv").write_text("start_s,end_s\n0,2\n")
    settings = run_cli(monkeypatch, tmp_path, make_video, "--footage-note", "Filmed in Oulu, January 2026.")
    assert settings.footage_note == "Filmed in Oulu, January 2026."


# --- start-up line and the card's threshold ---

def test_start_up_line_says_when_a_card_was_dropped(monkeypatch, tmp_path, make_video, capsys):
    run_auto(monkeypatch, tmp_path, make_video, {"kind": "student", "name": "older student"})
    out = capsys.readouterr().out
    assert "detector: student (model card ignored)" in out


def test_start_up_line_says_when_a_custom_student_dir_drops_the_card(monkeypatch, tmp_path, make_video, capsys):
    run_auto(monkeypatch, tmp_path, make_video, {"kind": "student", "name": "stub model"},
             "--student-dir", str(tmp_path))
    assert "detector: student (model card ignored)" in capsys.readouterr().out


@pytest.mark.parametrize("threshold", ["0.7", 1.5, -0.1, True, None, [0.5]])
def test_a_card_threshold_that_is_not_a_fraction_exits_2_naming_the_file(
        monkeypatch, tmp_path, make_video, capsys, threshold):
    with pytest.raises(SystemExit) as stop:
        run_auto(monkeypatch, tmp_path, make_video,
                 {"kind": "two_stage", "name": "stub model", "count_threshold": threshold})
    assert stop.value.code == 2
    assert str(tmp_path / "models" / "model_card.json") in capsys.readouterr().err


def test_a_card_threshold_of_nan_exits_2(monkeypatch, tmp_path, make_video):
    models = tmp_path / "models"
    write_card(models, kind="two_stage", name="stub model")
    card = models / "model_card.json"
    card.write_text(card.read_text().replace('"count_threshold": 0.7', '"count_threshold": NaN'))
    with pytest.raises(SystemExit) as stop:
        run_auto(monkeypatch, tmp_path, make_video, None, "--models-dir", str(models))
    assert stop.value.code == 2


# --- the latch ---


def test_latch_flag(monkeypatch, tmp_path, make_video, capsys):
    assert run_cli(monkeypatch, tmp_path, make_video).latch == "off"
    assert run_cli(monkeypatch, tmp_path, make_video, "--latch", "sim").latch == "sim"
    with pytest.raises(SystemExit) as exit_info:
        cli._parser().parse_args(["--videos", "x.mp4", "--latch", "on"])
    assert exit_info.value.code == 2


def test_router_latch_without_a_socket_still_starts(monkeypatch, tmp_path, make_video):
    from feeder_census.latch import RouterLatch

    given = {}

    class StubPipeline:
        error = None

        def __init__(self, camera, detector, store, settings, names, *args, latch=None, **kwargs):
            given.update(settings=settings, latch=latch, names=names, store=store)

        def run(self, stop):
            pass

    monkeypatch.setattr(cli, "Pipeline", StubPipeline)
    script = tmp_path / "script.json"
    script.write_text('{"species": ["great_tit", "red_squirrel"], "frames": [[]]}')
    argv = ["--videos", str(make_video()), "--detector", "scripted", "--script", str(script),
            "--db", str(tmp_path / "data" / "c.db"), "--no-web", "--latch", "router",
            "--latch-socket", str(tmp_path / "missing.sock")]
    assert cli.main(argv) == 0
    assert given["settings"].latch == "router"
    assert isinstance(given["latch"], RouterLatch) and given["latch"].socket_path == tmp_path / "missing.sock"
    assert given["names"]["red_squirrel"] == "Red squirrel"  # pests are drawn on the preview by name
    assert given["store"].species == ("great_tit",)  # never a census column


def test_no_web_line_says_what_the_latch_does(capsys):
    from datetime import datetime

    from feeder_census.latch import LatchState
    from feeder_census.pipeline import LiveState

    def line(latch):
        cli._print_line(LiveState(b"", datetime(2026, 11, 1, 8, 0), {"great_tit": 1}, {"great_tit": 1}, 0, 1.0,
                                  "scripted", {}, {}, latch, {"red_squirrel": 1}))
        return capsys.readouterr().out

    assert "latch" not in line(LatchState("off", False, None, None))
    assert "latch=closed (red_squirrel) error='no router socket'" in line(
        LatchState("router", True, "red_squirrel", "no router socket"))


# --- an old database meets a model with other species ---


def test_a_database_made_for_other_species_exits_1_with_one_line(monkeypatch, tmp_path, make_video, capsys):
    class StubPipeline:
        error = None

        def __init__(self, *args, **kwargs):
            pass

        def run(self, stop):
            pass

    monkeypatch.setattr(cli, "Pipeline", StubPipeline)
    video, db = make_video(), tmp_path / "data" / "c.db"

    def argv_for(species):
        script = tmp_path / f"{species}.json"
        script.write_text('{"species": ["%s"], "frames": [[]]}' % species)
        return ["--videos", str(video), "--detector", "scripted", "--script", str(script), "--db", str(db),
                "--no-web"]

    assert cli.main(argv_for("great_tit")) == 0
    capsys.readouterr()
    assert cli.main(argv_for("blue_tit")) == 1
    err = capsys.readouterr().err.strip()
    assert len(err.splitlines()) == 1
    assert "different species list" in err
    assert "--db" in err and "board/run.sh --fresh" in err


# --- the saved latch angles ---


def run_router_cli(monkeypatch, tmp_path, make_video, *extra, angles=None, fail_limits=False):
    """Runs main() with --latch router and a recording board link; returns (exit code, link calls, the latch state)."""
    from feeder_census import __main__ as module
    from feeder_census.latch import LatchError

    calls = []
    given = {}

    class RecordingLink:
        def __init__(self, socket_path, timeout_s=0.5):
            self.socket_path = socket_path

        def set(self, closed):
            calls.append(("set", closed))

        def set_limits(self, open_degrees, closed_degrees):
            calls.append(("limits", open_degrees, closed_degrees))
            if fail_limits:
                raise LatchError("no answer from the board")

    class StubPipeline:
        error = None

        def __init__(self, camera, detector, store, settings, names, *args, latch=None, **kwargs):
            given["latch"] = latch

        def run(self, stop):
            from feeder_census.latch import LatchController

            # the controller sends the open command as it is made, and reports a latch error instead of raising it
            given["state"] = LatchController(given["latch"], "router", order=[]).state

    monkeypatch.setattr(module, "Pipeline", StubPipeline)
    monkeypatch.setattr(module, "RouterLatch", RecordingLink)
    script = tmp_path / "script.json"
    script.write_text('{"species": ["great_tit"], "frames": [[]]}')
    data = tmp_path / "data"
    data.mkdir(exist_ok=True)
    if angles is not None:
        (data / "latch_angles.json").write_text(angles)
    argv = ["--videos", str(make_video()), "--detector", "scripted", "--script", str(script),
            "--db", str(data / "c.db"), "--no-web", "--latch", "router", "--latch-socket", str(tmp_path / "s"), *extra]
    return module.main(argv), calls, given.get("state")


def test_saved_angles_are_sent_before_the_first_latch_command(monkeypatch, tmp_path, make_video):
    code, calls, state = run_router_cli(monkeypatch, tmp_path, make_video, angles='{"open": 20, "closed": 150}')
    assert code == 0 and calls == [("limits", 20, 150), ("set", False)]


def test_without_an_angles_file_nothing_extra_is_sent(monkeypatch, tmp_path, make_video):
    code, calls, state = run_router_cli(monkeypatch, tmp_path, make_video)
    assert code == 0 and calls == [("set", False)]


def test_the_angles_file_can_be_named(monkeypatch, tmp_path, make_video):
    other = tmp_path / "mine.json"
    other.write_text('{"open": 5, "closed": 90}')
    code, calls, state = run_router_cli(monkeypatch, tmp_path, make_video, "--latch-angles", str(other))
    assert code == 0 and calls == [("limits", 5, 90), ("set", False)]


def test_a_failing_set_limits_does_not_stop_the_program(monkeypatch, tmp_path, make_video, capsys):
    code, calls, state = run_router_cli(
        monkeypatch, tmp_path, make_video, angles='{"open": 20, "closed": 150}', fail_limits=True
    )
    assert code == 0 and calls == [("limits", 20, 150), ("set", False)]  # the open command still went out
    assert state.error == "no answer from the board" and state.headline == "not_answering"


def test_a_broken_angles_file_is_a_warning_not_a_stop(monkeypatch, tmp_path, make_video, capsys):
    code, calls, state = run_router_cli(monkeypatch, tmp_path, make_video, angles="not json")
    assert code == 0 and calls == [("set", False)]
    assert "latch_angles.json" in capsys.readouterr().err


# --- the camera source: --camera instead of --videos ---

from feeder_census import camera as camera_module  # noqa: E402


def cli_argv(tmp_path, *source):
    script = tmp_path / "script.json"
    script.write_text('{"species": ["great_tit"], "frames": [[]]}')
    return [*source, "--detector", "scripted", "--script", str(script), "--db", str(tmp_path / "data" / "c.db"),
            "--no-web"]


def test_neither_videos_nor_camera_is_a_usage_error_naming_both(tmp_path, capsys):
    with pytest.raises(SystemExit) as stop:
        cli.main(cli_argv(tmp_path))
    err = capsys.readouterr().err
    assert stop.value.code == 2 and "--videos" in err and "--camera" in err


def test_both_videos_and_camera_is_a_usage_error_naming_both(tmp_path, make_video, capsys):
    with pytest.raises(SystemExit) as stop:
        cli.main(cli_argv(tmp_path, "--videos", str(make_video()), "--camera", "/dev/video4"))
    err = capsys.readouterr().err
    assert stop.value.code == 2 and "--videos" in err and "--camera" in err


def test_fast_with_camera_is_a_usage_error(tmp_path, capsys):
    with pytest.raises(SystemExit) as stop:
        cli.main(cli_argv(tmp_path, "--camera", "/dev/video4", "--fast"))
    err = capsys.readouterr().err
    assert stop.value.code == 2 and "--fast" in err and "--camera" in err


def test_camera_rotate_takes_only_0_or_180():
    with pytest.raises(SystemExit):
        cli._parser().parse_args(["--camera", "0", "--camera-rotate", "90"])
    assert cli._parser().parse_args(["--camera", "0"]).camera_rotate == 0


class _Unopened:
    def isOpened(self):
        return False

    def release(self):
        pass


def test_a_camera_that_cannot_open_exits_2_with_one_line_naming_the_device(monkeypatch, tmp_path, capsys):
    opened = []
    monkeypatch.setattr(camera_module, "_open_capture", lambda source: opened.append(source) or _Unopened())
    assert cli.main(cli_argv(tmp_path, "--camera", "/dev/video99")) == 2
    err = capsys.readouterr().err
    assert opened == ["/dev/video99"]
    assert err.strip().splitlines()[-1] == "error: cannot open camera /dev/video99" and "Traceback" not in err


def test_camera_source_reaches_the_settings_and_the_pipeline(monkeypatch, tmp_path):
    seen = {}

    class FakeLiveCamera:
        def __init__(self, device, rotate=0):
            seen["camera"] = (device, rotate)

    class StubPipeline:
        error = None

        def __init__(self, camera, detector, store, settings, *args, **kwargs):
            seen["settings"], seen["inline"] = settings, kwargs.get("inline")

        def run(self, stop):
            pass

    monkeypatch.setattr(cli, "LiveCamera", FakeLiveCamera)
    monkeypatch.setattr(cli, "Pipeline", StubPipeline)
    argv = cli_argv(tmp_path, "--camera", "/dev/video4", "--camera-rotate", "180", "--photo-every-s", "5")
    assert cli.main(argv) == 0
    s = seen["settings"]
    assert seen["camera"] == ("/dev/video4", 180) and seen["inline"] is False
    assert s.source == "camera" and s.photo_mode is True and s.detect_every_s == 5.0 and s.footage_note is None
    assert s.time_scale == Settings.time_scale


def test_videos_source_is_recorded(monkeypatch, tmp_path, make_video):
    assert run_cli(monkeypatch, tmp_path, make_video).source == "recorded"
