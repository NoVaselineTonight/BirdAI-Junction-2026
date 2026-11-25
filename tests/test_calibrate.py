import json
import threading
import urllib.error
import urllib.request

import pytest

from feeder_census.calibrate import make_server
from feeder_census.latch import LatchError


class FakeBoard:
    def __init__(self):
        self.calls: list[tuple] = []
        self.fail: str | None = None

    def _go(self, *call):
        self.calls.append(call)
        if self.fail:
            raise LatchError(self.fail)

    def set_angle(self, degrees):
        self._go("set_angle", degrees)
        return degrees

    def set_limits(self, open_degrees, closed_degrees):
        self._go("set_limits", open_degrees, closed_degrees)

    def set(self, closed):
        self._go("set", closed)


@pytest.fixture
def served(tmp_path):
    board = FakeBoard()
    angles = tmp_path / "data" / "latch_angles.json"
    server = make_server(board, angles, "127.0.0.1", 0)
    assert board.calls == [("set_limits", 180, 0)]  # sent once at the start, see the tests below
    board.calls.clear()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    yield base, board, angles
    server.shutdown()
    server.server_close()
    thread.join(5)


def request(base, path, body=None, raw=None, content_type="application/json"):
    data = raw if raw is not None else (None if body is None else json.dumps(body).encode())
    req = urllib.request.Request(base + path, data=data, method="GET" if data is None else "POST",
                                 headers={"Content-Type": content_type})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def call(base, path, body=None, raw=None, content_type="application/json"):
    status, data = request(base, path, body, raw, content_type)
    return status, json.loads(data)


def test_the_page_is_one_plain_html_document(served):
    base, _, _ = served
    status, data = request(base, "/")
    html = data.decode()
    assert status == 200 and html.lstrip().lower().startswith("<!doctype html>")
    for text in ("Save as OPEN", "Save as CLOSED", "Test: open", "Test: close", "Board not answering",
                 "color-scheme", "data/latch_angles.json"):
        assert text in html
    for outside in ("http://", "https://", "src=\"//"):
        assert outside not in html


def test_state_before_anything_is_set_shows_the_defaults(served):
    base, _, _ = served
    assert call(base, "/state") == (200, {"angle": None, "open": 180, "closed": 0, "saved": False, "error": None})


def test_state_shows_the_saved_angles(tmp_path):
    (tmp_path / "a.json").write_text('{"open": 150, "closed": 20}')
    board = FakeBoard()
    server = make_server(board, tmp_path / "a.json", "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        state = call(f"http://127.0.0.1:{server.server_address[1]}", "/state")[1]
    finally:
        server.shutdown()
        server.server_close()
    assert state["open"] == 150 and state["closed"] == 20 and state["saved"] is True
    assert board.calls == [("set_limits", 150, 20)]  # the saved angles went to the board at the start


def test_angle_turns_the_servo(served):
    base, board, _ = served
    assert call(base, "/angle", {"degrees": 95}) == (200, {"angle": 95})
    assert board.calls == [("set_angle", 95)]
    assert call(base, "/state")[1]["angle"] == 95
    assert call(base, "/angle", {"degrees": 0})[0] == 200 and call(base, "/angle", {"degrees": 180})[0] == 200


@pytest.mark.parametrize("body", [{"degrees": -1}, {"degrees": 181}, {"degrees": 1.5}, {"degrees": "90"},
                                  {"degrees": True}, {}, {"degrees": None}, [1]])
def test_angle_rejects_bad_values(served, body):
    base, board, _ = served
    status, reply = call(base, "/angle", body)
    assert status == 400 and reply["error"]
    assert board.calls == []


def test_angle_rejects_a_body_that_is_not_json(served):
    base, board, _ = served
    status, reply = call(base, "/angle", raw=b"{nope")
    assert status == 400 and reply["error"] and board.calls == []


def test_save_before_any_angle_is_refused(served):
    base, board, angles = served
    status, reply = call(base, "/save", {"which": "open"})
    assert status == 400 and "angle" in reply["error"]
    assert board.calls == [] and not angles.exists()


def test_save_writes_the_file_and_sends_the_limits(served):
    base, board, angles = served
    call(base, "/angle", {"degrees": 150})
    status, reply = call(base, "/save", {"which": "open"})
    assert status == 200 and reply == {"open": 150, "closed": 0, "saved": True}
    assert json.loads(angles.read_text()) == {"open": 150, "closed": 0}
    call(base, "/angle", {"degrees": 40})
    assert call(base, "/save", {"which": "closed"})[1]["closed"] == 40
    assert json.loads(angles.read_text()) == {"open": 150, "closed": 40}
    assert board.calls[-1] == ("set_limits", 150, 40)
    state = call(base, "/state")[1]
    assert (state["open"], state["closed"], state["saved"]) == (150, 40, True)


@pytest.mark.parametrize("which", ["both", "OPEN", None, 1])
def test_save_rejects_a_wrong_which(served, which):
    base, board, angles = served
    call(base, "/angle", {"degrees": 25})
    status, reply = call(base, "/save", {"which": which})
    assert status == 400 and reply["error"]
    assert board.calls == [("set_angle", 25)] and not angles.exists()


def test_test_runs_set_latch(served):
    base, board, _ = served
    assert call(base, "/test", {"closed": True})[0] == 200
    assert call(base, "/test", {"closed": False})[0] == 200
    assert board.calls == [("set", True), ("set", False)]
    assert call(base, "/test", {"closed": "yes"})[0] == 400
    assert call(base, "/test", {})[0] == 400
    assert len(board.calls) == 2


def test_a_board_that_does_not_answer_gives_502_and_the_server_carries_on(served):
    base, board, _ = served
    board.fail = "no answer from the board in 0.5 s"
    for path, body in (("/angle", {"degrees": 50}), ("/test", {"closed": True})):
        assert call(base, path, body) == (502, {"error": "no answer from the board in 0.5 s"})
    state = call(base, "/state")[1]
    assert state["error"] == "no answer from the board in 0.5 s" and state["angle"] is None
    board.fail = None
    assert call(base, "/angle", {"degrees": 50})[0] == 200
    assert call(base, "/state")[1]["error"] is None


def test_a_failed_set_limits_on_save_is_a_502(served):
    base, board, _ = served
    call(base, "/angle", {"degrees": 25})
    board.fail = "the board refused set_limits: nope"
    status, reply = call(base, "/save", {"which": "open"})
    assert status == 502 and "set_limits" in reply["error"]
    assert call(base, "/state")[0] == 200


def test_a_test_moves_the_current_angle_to_the_limit_it_used(served):
    base, board, angles = served
    call(base, "/angle", {"degrees": 160})
    call(base, "/save", {"which": "open"})
    call(base, "/angle", {"degrees": 25})
    call(base, "/save", {"which": "closed"})
    call(base, "/angle", {"degrees": 77})  # a hand-set angle, not a saved one
    assert call(base, "/test", {"closed": True}) == (200, {"closed": True, "angle": 25})
    assert call(base, "/state")[1]["angle"] == 25
    assert call(base, "/test", {"closed": False})[1]["angle"] == 160
    assert call(base, "/state")[1]["angle"] == 160
    assert call(base, "/test", {"closed": False})[0] == 200
    assert call(base, "/save", {"which": "closed"})[0] == 400  # where the servo is, the open angle: refused
    assert json.loads(angles.read_text()) == {"open": 160, "closed": 25}


def test_test_close_then_save_as_open_is_refused_and_nothing_changes(served):
    # the review's sequence: the page's angle becomes the closed angle (0), then "Save as OPEN" would write 0 / 0
    base, board, angles = served
    call(base, "/angle", {"degrees": 170})
    call(base, "/save", {"which": "open"})
    before = angles.read_text()
    assert call(base, "/test", {"closed": True}) == (200, {"closed": True, "angle": 0})
    calls_before = list(board.calls)
    status, reply = call(base, "/save", {"which": "open"})
    assert status == 400
    assert reply["error"].startswith("Not saved: the open angle must be at least 20 degrees above the closed angle, "
                                     "or the hatch could stay shut.")
    assert angles.read_text() == before and board.calls == calls_before  # nothing written, nothing sent
    state = call(base, "/state")[1]
    assert (state["open"], state["closed"]) == (170, 0)


def test_save_as_closed_too_close_to_the_open_angle_is_refused(served):
    base, board, angles = served
    call(base, "/angle", {"degrees": 161})
    status, reply = call(base, "/save", {"which": "closed"})  # default open 180: 161 is only 19 below
    assert status == 400 and reply["error"].startswith("Not saved:") and not angles.exists()
    call(base, "/angle", {"degrees": 160})
    assert call(base, "/save", {"which": "closed"}) == (200, {"open": 180, "closed": 160, "saved": True})


def test_the_page_shows_a_refused_save_in_plain_words(served):
    html = request(served[0], "/")[1].decode()
    assert "if (!r.ok) { say(data.error" in html  # a 400 reply's error text is what the page says


def test_the_saved_limits_go_to_the_board_once_at_the_start(tmp_path):
    (tmp_path / "a.json").write_text('{"open": 170, "closed": 10}')
    board = FakeBoard()
    server = make_server(board, tmp_path / "a.json", "127.0.0.1", 0)
    server.server_close()
    assert board.calls == [("set_limits", 170, 10)]


def test_a_board_that_does_not_answer_at_the_start_does_not_stop_the_page(tmp_path):
    (tmp_path / "a.json").write_text('{"open": 170, "closed": 10}')
    board = FakeBoard()
    board.fail = "no answer from the board in 0.5 s"
    server = make_server(board, tmp_path / "a.json", "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, state = call(f"http://127.0.0.1:{server.server_address[1]}", "/state")
    finally:
        server.shutdown()
        server.server_close()
    assert status == 200 and (state["open"], state["closed"]) == (170, 10)
    assert state["error"] == "no answer from the board in 0.5 s"


def test_an_angles_file_that_could_leave_the_hatch_shut_starts_the_page_with_the_defaults(tmp_path, capsys):
    (tmp_path / "a.json").write_text('{"open": 0, "closed": 0}')
    board = FakeBoard()
    server = make_server(board, tmp_path / "a.json", "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        state = call(f"http://127.0.0.1:{server.server_address[1]}", "/state")[1]
    finally:
        server.shutdown()
        server.server_close()
    assert (state["open"], state["closed"], state["saved"]) == (180, 0, False)
    assert board.calls == [("set_limits", 180, 0)]
    assert "a.json" in capsys.readouterr().err


def test_a_failed_test_leaves_the_current_angle_alone(served):
    base, board, _ = served
    call(base, "/angle", {"degrees": 77})
    board.fail = "no answer"
    assert call(base, "/test", {"closed": True})[0] == 502
    assert call(base, "/state")[1]["angle"] == 77


@pytest.mark.parametrize("content_type", ["text/plain", "application/x-www-form-urlencoded", "text/plain;charset=UTF-8"])
@pytest.mark.parametrize("path, body", [("/angle", {"degrees": 50}), ("/save", {"which": "open"}),
                                        ("/test", {"closed": True})])
def test_posts_that_are_not_json_are_refused_with_415(served, path, body, content_type):
    base, board, angles = served
    status, reply = call(base, path, body, content_type=content_type)
    assert status == 415 and "application/json" in reply["error"]
    assert board.calls == [] and not angles.exists()


def test_json_content_type_may_carry_a_charset(served):
    base, board, _ = served
    assert call(base, "/angle", {"degrees": 50}, content_type="application/json; charset=utf-8")[0] == 200
    assert board.calls == [("set_angle", 50)]


def test_the_page_says_a_hand_set_angle_is_reopened_after_ten_minutes(served):
    html = request(served[0], "/")[1].decode()
    assert "10 minutes" in html and "reopens a test close by itself after 30 s" not in html


def test_unknown_paths_are_404(served):
    base, _, _ = served
    assert request(base, "/nope")[0] == 404
    assert request(base, "/nope", {})[0] == 404


def test_the_command_line_refuses_a_broken_angles_file(tmp_path, capsys):
    from feeder_census import calibrate

    bad = tmp_path / "latch_angles.json"
    bad.write_text("not json")
    assert calibrate.main(["--port", "0", "--angles-file", str(bad)]) == 1
    assert "latch_angles.json" in capsys.readouterr().err
