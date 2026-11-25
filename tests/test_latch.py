import socket
import threading

import pytest

from feeder_census.latch import (
    DEFAULT_CLOSED, DEFAULT_OPEN, MIN_OPEN_ABOVE_CLOSED, AnglesLatch, LatchController, LatchError, RouterLatch,
    load_angles, pack_request, save_angles, unpack,
)

SQ = {"red_squirrel": 1, "brown_rat": 0}
CLEAR = {"red_squirrel": 0, "brown_rat": 0}


class FakeLatch:
    def __init__(self, fail: list[str | None] | None = None):
        self.calls: list[bool] = []
        self._fail = list(fail or [])

    def set(self, closed: bool) -> None:
        self.calls.append(closed)
        if self._fail:
            message = self._fail.pop(0)
            if message is not None:
                raise LatchError(message)


def test_closes_after_two_detections_and_reopens_after_five_clear():
    c = LatchController(FakeLatch(), "router")
    assert c.update(SQ).closed is False
    state = c.update(SQ)
    assert state.closed is True and state.reason == "red_squirrel" and state.error is None
    for _ in range(4):
        assert c.update(CLEAR).closed is True
    state = c.update(CLEAR)
    assert state.closed is False and state.reason is None
    assert c.state == state


def test_one_clear_detection_does_not_open():
    c = LatchController(FakeLatch(), "router")
    c.update(SQ), c.update(SQ)
    assert c.update(CLEAR).closed is True
    assert c.update(SQ).closed is True
    for _ in range(4):
        assert c.update(CLEAR).closed is True  # the count of clear detections started over
    assert c.update(CLEAR).closed is False


def test_a_single_pest_detection_does_not_close():
    latch = FakeLatch()
    c = LatchController(latch, "router")
    for frame in (SQ, CLEAR, SQ, CLEAR):
        assert c.update(frame).closed is False
    assert latch.calls == [False]  # only the open command sent at start-up


def test_close_is_resent_at_every_detection_while_closed():
    latch = FakeLatch()
    c = LatchController(latch, "router")
    for frame in (SQ, SQ, SQ, CLEAR, CLEAR, CLEAR, CLEAR, CLEAR, CLEAR, CLEAR):
        c.update(frame)
    # open at start-up; closed at the 2nd detection, still closed through the 3rd to the 7th (4 clear),
    # opened at the 8th
    assert latch.calls == [False] + [True] * 6 + [False]


def test_hardware_error_is_reported_and_the_rule_carries_on():
    latch = FakeLatch(fail=[None, "no socket", None])
    c = LatchController(latch, "router")
    c.update(SQ)
    state = c.update(SQ)
    assert state.closed is True and state.error == "no socket" and state.mode == "router"
    state = c.update(SQ)
    assert state.closed is True and state.error is None
    assert latch.calls == [False, True, True]


def test_a_failed_open_is_tried_again_at_the_next_detection():
    latch = FakeLatch(fail=[None, None, "timed out", None])
    c = LatchController(latch, "router", close_frames=1, open_frames=1)
    c.update(SQ)
    state = c.update(CLEAR)
    assert state.closed is False and state.error == "timed out"
    state = c.update(CLEAR)
    assert state.error is None
    c.update(CLEAR)
    assert latch.calls == [False, True, False, False]


def test_any_exception_from_the_latch_is_caught():
    class Broken:
        def set(self, closed):
            raise RuntimeError

    c = LatchController(Broken(), "router", close_frames=1)
    assert c.state.error == "RuntimeError"  # the start-up open command already failed
    state = c.update(SQ)
    assert state.closed is True and state.error == "RuntimeError"


def test_off_mode_never_closes_and_sim_mode_follows_the_rule_without_hardware():
    off = LatchController(None, "off")
    for _ in range(5):
        state = off.update(SQ)
    assert state == off.state and (state.mode, state.closed, state.reason, state.error) == ("off", False, None, None)
    sim = LatchController(None, "sim")
    sim.update(SQ)
    state = sim.update(SQ)
    assert (state.mode, state.closed, state.reason, state.error) == ("sim", True, "red_squirrel", None)


def test_reason_is_the_first_pest_in_species_order():
    c = LatchController(None, "sim", close_frames=1)
    assert c.update({"brown_rat": 1, "red_squirrel": 2}).reason == "red_squirrel"
    c = LatchController(None, "sim", close_frames=1)
    assert c.update({"brown_rat": 1, "red_squirrel": 0}).reason == "brown_rat"


def test_reason_follows_the_pest_that_is_there_and_stays_while_none_is():
    c = LatchController(None, "sim", close_frames=1)
    c.update({"red_squirrel": 1, "brown_rat": 0})
    assert c.update({"red_squirrel": 0, "brown_rat": 1}).reason == "brown_rat"
    assert c.update(CLEAR).reason == "brown_rat"


def test_pests_of_different_kinds_in_a_row_close_it():
    c = LatchController(None, "sim")
    c.update({"red_squirrel": 1, "brown_rat": 0})
    assert c.update({"red_squirrel": 0, "brown_rat": 1}).closed is True


def test_unknown_modes_are_refused():
    with pytest.raises(ValueError):
        LatchController(None, "on")
    with pytest.raises(ValueError):
        LatchController(None, "router")  # router needs hardware to talk to


def test_pack_request_bytes():
    assert pack_request(1, "set_latch", [True]) == bytes.fromhex("940001a97365745f6c6174636891c3")
    assert pack_request(5, "set_latch", [False]) == bytes.fromhex("940005a97365745f6c6174636891c2")
    assert pack_request(2, "get_latch", []) == bytes.fromhex("940002a9") + b"get_latch" + bytes.fromhex("90")
    with pytest.raises(LatchError):
        pack_request(256, "set_latch", [True])
    with pytest.raises(LatchError):
        pack_request(1, "x" * 32, [])
    with pytest.raises(LatchError):
        pack_request(1, "set_latch", [1.5])


def test_unpack_reply():
    assert unpack(bytes.fromhex("940101c0c0")) == [1, 1, None, None]
    assert unpack(bytes.fromhex("940101c0c3")) == [1, 1, None, True]
    assert unpack(bytes.fromhex("ccff")) == 255
    assert unpack(bytes.fromhex("cd0102")) == 258
    assert unpack(bytes.fromhex("ce00010000")) == 65536
    assert unpack(bytes.fromhex("d903") + b"abc") == "abc"
    assert unpack(bytes.fromhex("92ccfea3") + b"bad") == [254, "bad"]
    for garbage in ("", "94", "940101c0", "c1", "ff", "cb3ff0000000000000", "940101c0c0c0", "d905616263"):
        with pytest.raises(LatchError):
            unpack(bytes.fromhex(garbage))


def serve_once(path, reply_for, accept_timeout=5.0):
    """A Unix socket at `path` answering one request; returns (thread, list of requests received)."""
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(path))
    server.listen(1)
    server.settimeout(accept_timeout)
    seen: list[bytes] = []

    def run():
        try:
            conn, _ = server.accept()
        except OSError:
            return
        with conn:
            conn.settimeout(accept_timeout)
            data = conn.recv(256)
            seen.append(data)
            reply = reply_for(data)
            if reply is not None:
                # in two pieces, as a stream socket may deliver it
                conn.sendall(reply[:2])
                conn.sendall(reply[2:])
            else:
                conn.recv(1)  # say nothing until the client gives up
        server.close()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread, seen


def test_router_latch_talks_to_a_socket(tmp_path):
    path = tmp_path / "router.sock"
    thread, seen = serve_once(path, lambda req: bytes([0x94, 0x01, req[2], 0xC0, 0xC0]))
    RouterLatch(path).set(True)
    thread.join(5)
    (request,) = seen
    msgid = request[2]
    assert request == pack_request(msgid, "set_latch", [True])


def test_router_latch_errors(tmp_path):
    with pytest.raises(LatchError, match="no router socket"):
        RouterLatch(tmp_path / "missing.sock").set(True)

    path = tmp_path / "error.sock"
    thread, _ = serve_once(path, lambda req: bytes([0x94, 0x01, req[2], 0x92, 0xCC, 0xFE, 0xA3]) + b"nop" + b"\xc0")
    with pytest.raises(LatchError, match="nop"):
        RouterLatch(path).set(False)
    thread.join(5)

    path = tmp_path / "silent.sock"
    thread, _ = serve_once(path, lambda req: None)
    with pytest.raises(LatchError, match="no answer"):
        RouterLatch(path, timeout_s=0.2).set(True)
    thread.join(5)

    path = tmp_path / "wrong.sock"
    thread, _ = serve_once(path, lambda req: bytes([0x94, 0x01, (req[2] + 1) % 128, 0xC0, 0xC0]))
    with pytest.raises(LatchError, match="reply"):
        RouterLatch(path).set(True)
    thread.join(5)

    path = tmp_path / "closed.sock"
    thread, _ = serve_once(path, lambda req: b"\x94\x01")
    with pytest.raises(LatchError):
        RouterLatch(path, timeout_s=0.5).set(True)
    thread.join(5)


def test_latch_errors_are_os_errors():
    assert issubclass(LatchError, OSError)


def test_command_line_cycle_reports_what_the_board_said(tmp_path, monkeypatch, capsys):
    from feeder_census import latch as module

    sent = []

    class Recorder:
        def __init__(self, socket_path, timeout_s=0.5):
            sent.append(("socket", socket_path))

        def set(self, closed):
            sent.append(closed)

    monkeypatch.setattr(module, "RouterLatch", Recorder)
    monkeypatch.setattr(module.time, "sleep", lambda s: sent.append(("sleep", s)))
    assert module.main(["cycle", "--socket", str(tmp_path / "s")]) == 0
    assert sent == [("socket", tmp_path / "s"), True, ("sleep", 2.0), False]
    assert "closed" in capsys.readouterr().out


def test_command_line_exits_1_on_a_latch_error(tmp_path, capsys):
    from feeder_census import latch as module

    assert module.main(["close", "--socket", str(tmp_path / "missing.sock")]) == 1
    assert "no router socket" in capsys.readouterr().err


def test_router_mode_confirms_the_open_latch_at_start_up():
    latch = FakeLatch()
    c = LatchController(latch, "router")
    assert latch.calls == [False] and c.state.error is None and c.state.headline == "open"
    unplugged = LatchController(FakeLatch(fail=["no router socket"]), "router")
    assert unplugged.state.error == "no router socket" and unplugged.state.headline == "not_answering"
    assert LatchController(FakeLatch(), "sim").state.headline == "open"  # sim never talks to hardware


def test_headline_never_claims_a_state_the_hardware_did_not_confirm():
    from feeder_census.latch import LatchState

    assert LatchState("sim", False, None, None).headline == "open"
    assert LatchState("sim", True, "red_squirrel", None).headline == "closed"
    assert LatchState("router", False, None, None).headline == "open"
    assert LatchState("router", True, "red_squirrel", None).headline == "closed"
    assert LatchState("router", True, "red_squirrel", "timed out").headline == "not_answering"
    assert LatchState("router", False, None, "timed out").headline == "not_answering"
    assert LatchState("off", False, None, None).headline == "off"


def test_a_failed_open_after_a_close_is_not_shown_as_open():
    latch = FakeLatch(fail=[None, None, "timed out"])
    c = LatchController(latch, "router", close_frames=1, open_frames=1)
    assert c.update(SQ).headline == "closed"
    state = c.update(CLEAR)
    assert (state.closed, state.error, state.headline) == (False, "timed out", "not_answering")


# --- angles: packing, the router calls, the saved file ---


def test_pack_ints_up_to_255_as_uint8():
    assert pack_request(1, "a", [127]) == bytes.fromhex("940001a161") + bytes.fromhex("917f")
    assert pack_request(1, "a", [128]) == bytes.fromhex("940001a161") + bytes.fromhex("91cc80")
    assert pack_request(1, "a", [180]) == bytes.fromhex("940001a161") + bytes.fromhex("91ccb4")
    assert pack_request(1, "a", [255]) == bytes.fromhex("940001a161") + bytes.fromhex("91ccff")
    assert pack_request(1, "a", [0]) == bytes.fromhex("940001a161") + bytes.fromhex("9100")
    for bad in (256, -1):
        with pytest.raises(LatchError):
            pack_request(1, "a", [bad])


def test_a_uint8_reply_is_read_back():
    assert unpack(bytes.fromhex("940101c0ccb4")) == [1, 1, None, 180]


def serve_script(path, replies):
    """A Unix socket that answers len(replies) requests, one per connection; returns (thread, requests seen)."""
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(path))
    server.listen(1)
    server.settimeout(5.0)
    seen: list[bytes] = []

    def run():
        for result in replies:
            try:
                conn, _ = server.accept()
            except OSError:
                break
            with conn:
                data = conn.recv(256)
                seen.append(data)
                conn.sendall(bytes([0x94, 0x01, data[2], 0xC0]) + result)
        server.close()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread, seen


def test_set_angle_get_angle_and_set_limits_send_the_right_calls(tmp_path):
    path = tmp_path / "router.sock"
    thread, seen = serve_script(path, [b"\xcc\xb4", b"\x5a", b"\xc3"])
    link = RouterLatch(path)
    assert link.set_angle(180) == 180
    assert link.get_angle() == 90
    assert link.set_limits(20, 150) is None
    thread.join(5)
    assert [r[3:] for r in seen] == [
        b"\xa9set_angle\x91\xcc\xb4", b"\xa9get_angle\x90", b"\xaaset_limits\x92\x14\xcc\x96",
    ]


@pytest.mark.parametrize("bad", [-1, 181, 1.5, "90", True, None])
def test_set_angle_rejects_bad_values_without_sending(tmp_path, bad):
    link = RouterLatch(tmp_path / "missing.sock")
    with pytest.raises(ValueError):
        link.set_angle(bad)  # a LatchError (no socket) would mean it tried to send


@pytest.mark.parametrize("pair", [(-1, 100), (10, 181), (1.5, 100), (10, "100"), (True, 100), (10, False)])
def test_set_limits_rejects_bad_values_without_sending(tmp_path, pair):
    with pytest.raises(ValueError):
        RouterLatch(tmp_path / "missing.sock").set_limits(*pair)


def test_get_angle_that_is_not_a_number_is_a_latch_error(tmp_path):
    path = tmp_path / "router.sock"
    thread, _ = serve_script(path, [b"\xc3"])
    with pytest.raises(LatchError, match="get_angle"):
        RouterLatch(path).get_angle()
    thread.join(5)


def test_angles_file_round_trip(tmp_path):
    path = tmp_path / "data" / "latch_angles.json"
    assert load_angles(path) is None
    save_angles(path, 150, 20)
    assert load_angles(path) == (150, 20)
    assert path.read_text().strip() == '{"open": 150, "closed": 20}'
    save_angles(path, 180, 0)
    assert load_angles(path) == (180, 0)
    save_angles(path, 20, 0)  # exactly MIN_OPEN_ABOVE_CLOSED apart is allowed
    assert load_angles(path) == (20, 0)


@pytest.mark.parametrize("text", ['{"open": 0, "closed": 0}', '{"open": 19, "closed": 0}', '{"open": 0, "closed": 180}',
                                  '{"open": 100, "closed": 90}'])
def test_an_angles_file_that_could_leave_the_hatch_shut_gives_the_defaults_and_says_so(tmp_path, text):
    path = tmp_path / "latch_angles.json"
    path.write_text(text)
    said = []
    assert load_angles(path, warn=said.append) == (DEFAULT_OPEN, DEFAULT_CLOSED) == (180, 0)
    assert len(said) == 1 and "latch_angles.json" in said[0] and "at least 20 degrees" in said[0]


def test_an_angles_file_that_could_leave_the_hatch_shut_is_reported_on_stderr_by_default(tmp_path, capsys):
    path = tmp_path / "latch_angles.json"
    path.write_text('{"open": 0, "closed": 0}')
    assert load_angles(path) == (180, 0)
    assert "latch_angles.json" in capsys.readouterr().err


@pytest.mark.parametrize("pair", [(0, 0), (19, 0), (0, 180), (100, 90)])
def test_save_angles_refuses_a_pair_that_could_leave_the_hatch_shut(tmp_path, pair):
    path = tmp_path / "latch_angles.json"
    with pytest.raises(ValueError, match="at least 20 degrees"):
        save_angles(path, *pair)
    assert not path.exists()


@pytest.mark.parametrize("text", [
    "not json", "[]", "{}", '{"open": 10}', '{"open": 10, "closed": 181}', '{"open": -1, "closed": 100}',
    '{"open": 1.5, "closed": 100}', '{"open": "10", "closed": 100}', '{"open": true, "closed": 100}',
])
def test_a_broken_angles_file_is_a_latch_error_naming_the_file(tmp_path, text):
    path = tmp_path / "latch_angles.json"
    path.write_text(text)
    with pytest.raises(LatchError, match="latch_angles.json"):
        load_angles(path)


def test_save_angles_rejects_bad_values_and_writes_nothing(tmp_path):
    path = tmp_path / "latch_angles.json"
    with pytest.raises(ValueError):
        save_angles(path, 10, 181)
    assert not path.exists()


class FakeAngleLink(FakeLatch):
    def __init__(self, fail_limits: list[str | None] | None = None):
        super().__init__()
        self.limits: list[tuple[int, int]] = []
        self.order: list[object] = []
        self._fail_limits = list(fail_limits or [])

    def set(self, closed):
        self.order.append(("set", closed))
        super().set(closed)

    def set_limits(self, open_degrees, closed_degrees):
        self.order.append(("limits", open_degrees, closed_degrees))
        self.limits.append((open_degrees, closed_degrees))
        if self._fail_limits:
            message = self._fail_limits.pop(0)
            if message is not None:
                raise LatchError(message)


def test_angles_latch_sends_the_limits_before_the_first_command_only():
    link = FakeAngleLink()
    wrapped = AnglesLatch(link, (20, 150))
    wrapped.set(False)
    wrapped.set(True)
    assert link.order == [("limits", 20, 150), ("set", False), ("set", True)]


def test_a_failing_set_limits_is_reported_but_the_latch_still_moves_and_is_tried_again():
    link = FakeAngleLink(fail_limits=["no answer", None])
    c = LatchController(AnglesLatch(link, (20, 150)), "router", close_frames=1)
    assert c.state.error == "no answer"  # shown like any other latch error
    assert link.calls == [False]  # the open command still went out
    state = c.update(SQ)
    assert state.closed is True and state.error is None
    assert link.limits == [(20, 150), (20, 150)]
    c.update(SQ)
    assert link.limits == [(20, 150), (20, 150)]  # sent once it worked


def test_the_hatch_rule_is_twenty_degrees():
    assert MIN_OPEN_ABOVE_CLOSED == 20


def test_the_default_angles_match_the_sketch():
    import re
    from pathlib import Path

    sketch = (Path(__file__).resolve().parents[1] / "board" / "latch" / "latch.ino").read_text()
    found = {name: int(value) for name, value in re.findall(r"\b(servoOpen|servoClosed)\s*=\s*(\d+)", sketch)}
    assert found == {"servoOpen": DEFAULT_OPEN, "servoClosed": DEFAULT_CLOSED}
