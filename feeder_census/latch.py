"""The feeder latch: closes when a squirrel or rat is at the feeder, opens again when it has gone.

`LatchController` holds the rule; `RouterLatch` sends the command to the UNO Q's microcontroller
through the arduino-router service (MessagePack-RPC on a Unix socket), where board/latch/latch.ino
moves the servo. Bring the hardware up by hand with:

    python -m feeder_census.latch close|open|cycle|angle N [--socket PATH]

The open and closed angles can be set from a browser (feeder_census.calibrate) and are kept in a small
JSON file, see load_angles / save_angles.
"""
import argparse
import json
import itertools
import socket
import struct
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

MODES = ("off", "sim", "router")
ROUTER_SOCKET = Path("/var/run/arduino-router.sock")
DEFAULT_OPEN, DEFAULT_CLOSED = 180, 0  # the sketch's own start values (board/latch/latch.ino)
MAX_DEGREES = 180


class LatchError(OSError):
    """The latch command did not go through. The message says what to check."""


class Latch(Protocol):
    def set(self, closed: bool) -> None: ...  # may raise OSError / LatchError


@dataclass(frozen=True)
class LatchState:
    mode: str  # "off" | "sim" | "router"
    closed: bool
    reason: str | None  # pest key that closed it, None when open
    error: str | None  # last hardware error text, None when the last command went through

    @property
    def headline(self) -> str:
        """What the page may say: "off", "open", "closed", or "not_answering" when the board did not confirm
        the last command (router mode). The page never calls the latch open or closed unconfirmed."""
        if self.mode == "off":
            return "off"
        if self.mode == "router" and self.error is not None:
            return "not_answering"
        return "closed" if self.closed else "open"


class LatchController:
    """Closes after `close_frames` detections in a row with a pest in frame, opens after `open_frames` without.

    In router mode an open command goes out when the controller is made, so the page's "open" is
    confirmed from the start. While closed the close command is sent again at every detection: the
    sketch reopens by itself when it stops hearing it. A command that fails is reported in
    `state.error` and tried again at the next detection; it never stops the caller.
    """

    def __init__(
        self, latch: Latch | None, mode: str, close_frames: int = 2, open_frames: int = 5,
        *, order: Sequence[str] | None = None,
    ):
        if mode not in MODES:
            raise ValueError(f"latch mode must be one of {', '.join(MODES)}, got {mode!r}")
        if mode == "router" and latch is None:
            raise ValueError("latch mode 'router' needs a latch to send commands to")
        if order is None:
            from feeder_census.species import load_pests

            order = [p.key for p in load_pests()]
        self._latch = latch if mode == "router" else None
        self._close_frames, self._open_frames = max(1, close_frames), max(1, open_frames)
        self._order = list(order)
        self._seen = 0  # detections in a row with a pest in frame
        self._clear = 0  # detections in a row without one
        self._resend = False  # the last command failed; send the state again
        self._state = LatchState(mode, False, None, None)
        if self._latch is not None:  # confirm the open latch now, or show at once that the board is not answering
            self._state = LatchState(mode, False, None, self._send(False))

    @property
    def state(self) -> LatchState:
        return self._state

    def update(self, pests_in_frame: Mapping[str, int]) -> LatchState:
        s = self._state
        if s.mode == "off":
            return s
        rank = {key: i for i, key in enumerate(self._order)}
        present = sorted((k for k, n in pests_in_frame.items() if n > 0), key=lambda k: rank.get(k, len(rank)))
        if present:
            self._seen, self._clear = self._seen + 1, 0
        else:
            self._seen, self._clear = 0, self._clear + 1
        closed, reason = s.closed, s.reason
        if not closed and self._seen >= self._close_frames:
            closed = True
        elif closed and self._clear >= self._open_frames:
            closed = False
        if closed and present:
            reason = present[0]
        elif not closed:
            reason = None
        error = s.error
        if self._latch is not None and (closed or closed != s.closed or self._resend):
            error = self._send(closed)
        self._state = LatchState(s.mode, closed, reason, error)
        return self._state

    def _send(self, closed: bool) -> str | None:
        try:
            self._latch.set(closed)
        except Exception as exc:  # a latch fault must never stop the counting
            self._resend = True
            return str(exc) or type(exc).__name__
        self._resend = False
        return None


# --- MessagePack, just the few types the router call needs ---


def _pack(value: object) -> bytes:
    if value is None:
        return b"\xc0"
    if isinstance(value, bool):
        return b"\xc3" if value else b"\xc2"
    if isinstance(value, int) and 0 <= value <= 127:
        return bytes([value])
    if isinstance(value, int) and 128 <= value <= 255:
        return bytes([0xCC, value])  # uint 8
    if isinstance(value, str):
        raw = value.encode()
        if len(raw) < 32:
            return bytes([0xA0 | len(raw)]) + raw
    if isinstance(value, (list, tuple)) and len(value) < 16:
        return bytes([0x90 | len(value)]) + b"".join(_pack(v) for v in value)
    raise LatchError(f"cannot send {value!r} to the board (only nil, bool, 0-255, short strings and lists)")


def pack_request(msgid: int, method: str, args: list) -> bytes:
    """A MessagePack-RPC request: [0, msgid, method, args]."""
    return _pack([0, msgid, method, list(args)])


class _Incomplete(LatchError):
    """The bytes end before the value does: more may still arrive."""


def _take(data: bytes, at: int, n: int) -> bytes:
    if at + n > len(data):
        raise _Incomplete("the reply from the board ended too early")
    return data[at : at + n]


def _unpack_at(data: bytes, at: int) -> tuple[object, int]:
    b = _take(data, at, 1)[0]
    at += 1
    if b == 0xC0:
        return None, at
    if b in (0xC2, 0xC3):
        return b == 0xC3, at
    if b <= 0x7F:
        return b, at
    if b in (0xCC, 0xCD, 0xCE):
        n = {0xCC: 1, 0xCD: 2, 0xCE: 4}[b]
        return int.from_bytes(_take(data, at, n), "big"), at + n
    if 0xA0 <= b <= 0xBF or b in (0xD9, 0xDA):
        if b == 0xD9:
            n, at = _take(data, at, 1)[0], at + 1
        elif b == 0xDA:
            n, at = struct.unpack(">H", _take(data, at, 2))[0], at + 2
        else:
            n = b & 0x1F
        raw = _take(data, at, n)
        try:
            return raw.decode(), at + n
        except UnicodeDecodeError:
            raise LatchError("the board's reply holds text that is not UTF-8")
    if 0x90 <= b <= 0x9F:
        items = []
        for _ in range(b & 0x0F):
            item, at = _unpack_at(data, at)
            items.append(item)
        return items, at
    raise LatchError(f"the board's reply holds a value this program cannot read (type byte 0x{b:02x})")


def unpack(data: bytes) -> object:
    """One MessagePack value filling all of `data`: nil, bool, unsigned ints, strings and arrays."""
    value, end = _unpack_at(data, 0)
    if end != len(data):
        raise LatchError(f"the board's reply has {len(data) - end} unexpected bytes after it")
    return value


# --- the saved open / closed angles ---


def _is_degrees(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= MAX_DEGREES


def _check_degrees(*values: object) -> None:
    for value in values:
        if not _is_degrees(value):
            raise ValueError(f"an angle must be a whole number from 0 to {MAX_DEGREES}, got {value!r}")


def load_angles(path: Path) -> tuple[int, int] | None:
    """The saved (open, closed) angles, or None when the file does not exist. A file that cannot be read or holds
    anything but `{"open": N, "closed": N}` with N from 0 to 180 raises LatchError naming the file."""
    path = Path(path)
    try:
        text = path.read_text()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise LatchError(f"cannot read {path}: {exc.strerror or exc}")
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise LatchError(f"{path} is not valid JSON ({exc}); delete it or save the angles again")
    if not (isinstance(data, dict) and _is_degrees(data.get("open")) and _is_degrees(data.get("closed"))):
        raise LatchError(f'{path} must look like {{"open": 180, "closed": 0}} with angles from 0 to {MAX_DEGREES}, '
                         f"got {text.strip()[:80]!r}")
    return data["open"], data["closed"]


def save_angles(path: Path, open_degrees: int, closed_degrees: int) -> None:
    """Writes the angles file (parent folder made when missing); the old file stays whole if the write fails."""
    _check_degrees(open_degrees, closed_degrees)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps({"open": open_degrees, "closed": closed_degrees}) + "\n")
    tmp.replace(path)


class AnglesLatch:
    """Wraps a latch link that has `set_limits`: the saved angles go to the board before the first command.

    If `set_limits` fails the command is still sent (the board's own angles apply) and the failure is raised
    afterwards, so the controller reports it like any latch error; the angles are sent again with the next command.
    """

    def __init__(self, latch, angles: tuple[int, int]):
        self._latch, self._angles, self._limits_sent = latch, angles, False

    def set(self, closed: bool) -> None:
        limits_error = None
        if not self._limits_sent:
            try:
                self._latch.set_limits(*self._angles)
                self._limits_sent = True
            except LatchError as exc:
                limits_error = exc
        self._latch.set(closed)
        if limits_error is not None:
            raise limits_error


# --- the router link ---


class RouterLatch:
    """Calls `set_latch` on the microcontroller through arduino-router. One connection per call."""

    def __init__(self, socket_path: Path = ROUTER_SOCKET, timeout_s: float = 0.5):
        self.socket_path, self.timeout_s = Path(socket_path), timeout_s
        self._ids = itertools.cycle(range(128))

    def set(self, closed: bool) -> None:
        self.call("set_latch", [bool(closed)])

    def set_angle(self, degrees: int) -> int:
        """Starts turning the servo to `degrees` (0..180), 10 degrees every 0.1 s; returns the angle the board used."""
        _check_degrees(degrees)
        return self._int_result("set_angle", self.call("set_angle", [degrees]))

    def get_angle(self) -> int:
        """The angle the servo is going to or has reached (the board's target)."""
        return self._int_result("get_angle", self.call("get_angle", []))

    def set_limits(self, open_degrees: int, closed_degrees: int) -> None:
        """Gives the board its open and closed angles (kept there until it restarts)."""
        _check_degrees(open_degrees, closed_degrees)
        self.call("set_limits", [open_degrees, closed_degrees])

    @staticmethod
    def _int_result(method: str, result: object) -> int:
        if not _is_int(result):
            raise LatchError(f"the board answered {method} with {result!r}, not an angle")
        return result

    def call(self, method: str, args: list) -> object:
        """Sends one request and returns the board's result; any failure raises LatchError."""
        msgid = next(self._ids)
        request = pack_request(msgid, method, args)
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(self.timeout_s)
            try:
                sock.connect(str(self.socket_path))
            except FileNotFoundError:
                raise LatchError(f"no router socket at {self.socket_path}")  # short: the page shows it
            except PermissionError:
                raise LatchError(f"no permission to open {self.socket_path}")
            except OSError as exc:
                raise LatchError(f"cannot connect to {self.socket_path}: {exc.strerror or exc}")
            reply = self._read_reply(sock, request, method)
        if not (isinstance(reply, list) and len(reply) == 4 and reply[0] == 1):
            raise LatchError(f"the router sent something that is not a reply: {reply!r}")
        if reply[1] != msgid:
            raise LatchError(f"the router's reply is for request {reply[1]!r}, not {msgid}")
        if reply[2] is not None:
            raise LatchError(f"the board refused {method}: {_error_text(reply[2])}")
        return reply[3]

    def _read_reply(self, sock: socket.socket, request: bytes, method: str) -> object:
        data = b""
        try:
            sock.sendall(request)
            while True:
                chunk = sock.recv(512)
                if not chunk:
                    raise LatchError(f"the router closed the connection before answering {method}")
                data += chunk
                try:
                    return unpack(data)
                except _Incomplete:
                    continue
        except TimeoutError:
            raise LatchError(f"no answer from the board in {self.timeout_s:g} s")
        except LatchError:
            raise
        except OSError as exc:
            raise LatchError(f"lost the connection to {self.socket_path}: {exc.strerror or exc}")


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _error_text(error: object) -> str:
    if isinstance(error, list) and len(error) == 2:  # RPClite sends [code, traceback]
        return f"{error[1]} (code {error[0]})"
    return str(error)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m feeder_census.latch", description="Move the feeder latch by hand.")
    p.add_argument("command", choices=("close", "open", "cycle", "angle"),
                   help="cycle: close, wait 2 s, open; angle N: turn the servo to N degrees (0 to 180)")
    p.add_argument("degrees", nargs="?", type=int, help="for angle: where to turn the servo")
    p.add_argument("--socket", type=Path, default=ROUTER_SOCKET, help="arduino-router socket (default: %(default)s)")
    args = p.parse_args(argv)
    if (args.command == "angle") != (args.degrees is not None):
        p.error("angle needs a number of degrees (angle 90); the other commands take none")
    latch = RouterLatch(args.socket)
    if args.command == "angle":
        try:
            used = latch.set_angle(args.degrees)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        except LatchError as exc:
            print(f"error: {exc}", file=sys.stderr)
            print("check that the arduino-router service runs on the board and that board/latch/latch.ino is "
                  "uploaded (README.md, Latch)", file=sys.stderr)
            return 1
        print(f"angle: the board turned the servo to {used} degrees", flush=True)
        return 0
    steps = {"close": [True], "open": [False], "cycle": [True, None, False]}[args.command]
    try:
        for closed in steps:
            if closed is None:
                time.sleep(2.0)
                continue
            latch.set(closed)
            word = "closed" if closed else "opened"
            print(f"{word}: the board answered set_latch({str(closed).lower()}) without an error", flush=True)
    except LatchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        print("check that the arduino-router service runs on the board and that board/latch/latch.ino is uploaded "
              "(README.md, Latch)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
