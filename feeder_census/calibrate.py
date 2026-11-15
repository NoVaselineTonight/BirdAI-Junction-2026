"""A very simple web page to turn the latch servo by hand and save its open and closed angles.

    python -m feeder_census.calibrate [--port 8090] [--host 127.0.0.1] [--socket PATH] [--angles-file PATH]

Standard library only. The page talks JSON to this server, which talks to the board through
feeder_census.latch.RouterLatch (any object with the same three methods works, see `Board`). The saved angles
go to a small JSON file (default data/latch_angles.json) that `python -m feeder_census --latch router` sends
to the board at its start.
"""
import argparse
import json
import signal
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Protocol

from feeder_census.latch import (
    DEFAULT_CLOSED, DEFAULT_OPEN, MAX_DEGREES, ROUTER_SOCKET, LatchError, RouterLatch, load_angles, save_angles,
)

DEFAULT_ANGLES_FILE = Path("data/latch_angles.json")
DEFAULT_PORT = 8090
MAX_BODY = 1024


class Board(Protocol):
    def set_angle(self, degrees: int) -> int: ...
    def set_limits(self, open_degrees: int, closed_degrees: int) -> None: ...
    def set(self, closed: bool) -> None: ...  # set_latch; all may raise LatchError


class _BadRequest(Exception):
    pass


class Calibration:
    """What the page shows and does. One lock, so two phones at once cannot mix up the numbers."""

    def __init__(self, board: Board, angles_file: Path):
        self.board, self.angles_file = board, Path(angles_file)
        self.angle: int | None = None  # the last angle turned to in this session
        self.error: str | None = None
        self._lock = threading.Lock()
        saved = load_angles(self.angles_file)  # LatchError for a broken file: the caller says so and stops
        self.open, self.closed = saved if saved is not None else (DEFAULT_OPEN, DEFAULT_CLOSED)

    def state(self) -> dict:
        with self._lock:
            return {"angle": self.angle, "open": self.open, "closed": self.closed,
                    "saved": self.angles_file.exists(), "error": self.error}

    def set_angle(self, body: object) -> dict:
        degrees = body.get("degrees") if isinstance(body, dict) else None
        if not isinstance(degrees, int) or isinstance(degrees, bool) or not 0 <= degrees <= MAX_DEGREES:
            raise _BadRequest(f"degrees must be a whole number from 0 to {MAX_DEGREES}")
        with self._lock:
            used = self._board_call(self.board.set_angle, degrees)
            self.angle = used if isinstance(used, int) else degrees
            return {"angle": self.angle}

    def save(self, body: object) -> dict:
        which = body.get("which") if isinstance(body, dict) else None
        if which not in ("open", "closed"):
            raise _BadRequest('which must be "open" or "closed"')
        with self._lock:
            if self.angle is None:
                raise _BadRequest("turn the servo first: there is no angle to save yet")
            open_degrees, closed_degrees = (self.angle, self.closed) if which == "open" else (self.open, self.angle)
            try:
                save_angles(self.angles_file, open_degrees, closed_degrees)
            except OSError as exc:
                raise _ServerError(f"cannot write {self.angles_file}: {exc.strerror or exc}")
            self.open, self.closed = open_degrees, closed_degrees
            self._board_call(self.board.set_limits, open_degrees, closed_degrees)
            return {"open": self.open, "closed": self.closed, "saved": True}

    def test(self, body: object) -> dict:
        closed = body.get("closed") if isinstance(body, dict) else None
        if not isinstance(closed, bool):
            raise _BadRequest("closed must be true or false")
        with self._lock:
            self._board_call(self.board.set, closed)
            return {"closed": closed}

    def _board_call(self, method, *args):
        try:
            result = method(*args)
        except LatchError as exc:
            self.error = str(exc) or type(exc).__name__
            raise
        self.error = None
        return result


class _ServerError(Exception):
    pass


def _handler(cal: Calibration) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):  # quiet: one line per request would fill the board's log
            pass

        def _send(self, status: int, payload: object | bytes, content_type: str = "application/json") -> None:
            body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", f"{content_type}; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path == "/":
                self._send(200, PAGE.encode(), "text/html")
            elif path == "/state":
                self._send(200, cal.state())
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self):
            actions = {"/angle": cal.set_angle, "/save": cal.save, "/test": cal.test}
            action = actions.get(self.path.split("?", 1)[0])
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = -1
            if length < 0 or length > MAX_BODY:
                self.close_connection = True
                self._send(400, {"error": "the request body is missing or too long"})
                return
            raw = self.rfile.read(length)  # always read it, so the connection stays in step
            if action is None:
                self._send(404, {"error": "not found"})
                return
            try:
                body = json.loads(raw or b"null")
            except ValueError:
                self._send(400, {"error": "the request body is not JSON"})
                return
            try:
                self._send(200, action(body))
            except _BadRequest as exc:
                self._send(400, {"error": str(exc)})
            except LatchError as exc:
                self._send(502, {"error": str(exc) or type(exc).__name__})
            except _ServerError as exc:
                self._send(500, {"error": str(exc)})

    return Handler


def make_server(board: Board, angles_file: Path, host: str = "127.0.0.1", port: int = DEFAULT_PORT) -> ThreadingHTTPServer:
    """The page's server, not yet running (call serve_forever). Raises LatchError for a broken angles file."""
    server = ThreadingHTTPServer((host, port), _handler(Calibration(board, angles_file)))
    server.daemon_threads = True
    return server


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m feeder_census.calibrate",
                                description="A page to turn the latch servo by hand and save its open and closed angles.")
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--socket", type=Path, default=ROUTER_SOCKET, help="arduino-router socket (default: %(default)s)")
    p.add_argument("--angles-file", type=Path, default=DEFAULT_ANGLES_FILE,
                   help="where the saved angles are kept (default: %(default)s)")
    args = p.parse_args(argv)
    try:
        server = make_server(RouterLatch(args.socket), args.angles_file, args.host, args.port)
    except LatchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"error: cannot listen on {args.host}:{args.port}: {exc.strerror or exc}", file=sys.stderr)
        return 1
    signal.signal(signal.SIGTERM, lambda signum, frame: threading.Thread(target=server.shutdown).start())
    print(f"latch calibration page on http://{args.host}:{server.server_address[1]}  (angles file: {args.angles_file})",
          flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Latch angles</title>
<style>
  :root { color-scheme: light dark; }
  * { box-sizing: border-box; }
  body { font: 1.05rem/1.4 system-ui, sans-serif; margin: 0 auto; padding: 1rem; max-width: 30rem;
         background: Canvas; color: CanvasText; }
  h1 { font-size: 1.2rem; margin: 0 0 .5rem; }
  #angle { font-size: 5rem; font-weight: 700; text-align: center; line-height: 1.1; margin: .5rem 0; }
  #angle small { font-size: 1.5rem; font-weight: 400; }
  input[type=range] { width: 100%; height: 3rem; margin: .5rem 0 1rem; }
  .row { display: grid; gap: .5rem; margin-bottom: .75rem; }
  .four { grid-template-columns: repeat(4, 1fr); }
  .two { grid-template-columns: 1fr 1fr; }
  button { font: inherit; min-height: 3.25rem; padding: .5rem; border: 2px solid ButtonText; border-radius: .5rem;
           background: ButtonFace; color: ButtonText; }
  button:active { background: Highlight; color: HighlightText; }
  button small { display: block; font-size: .85rem; }
  #status { min-height: 3rem; padding: .6rem; border: 1px solid GrayText; border-radius: .5rem; margin: 1rem 0; }
  #status.bad { border: 2px solid; font-weight: 700; }
  p.note { font-size: .9rem; color: GrayText; }
</style>
</head>
<body>
<h1>Latch angles</h1>
<div id="angle" aria-live="polite">--<small> degrees</small></div>
<input id="slider" type="range" min="0" max="180" step="1" value="90" aria-label="Servo angle in degrees">
<div class="row four">
  <button data-step="-10">-10</button><button data-step="-1">-1</button>
  <button data-step="1">+1</button><button data-step="10">+10</button>
</div>
<div class="row two">
  <button id="save-open">Save as OPEN<small id="saved-open"></small></button>
  <button id="save-closed">Save as CLOSED<small id="saved-closed"></small></button>
</div>
<div class="row two">
  <button id="test-open">Test: open</button>
  <button id="test-close">Test: close</button>
</div>
<div id="status" role="status">Loading...</div>
<p class="note">The saved angles are kept on the board in data/latch_angles.json and the demo uses them at its next
start. To make them the sketch's own defaults, put the two numbers into the sketch.</p>
<script>
const slider = document.getElementById("slider"), big = document.getElementById("angle"), statusEl = document.getElementById("status");
let current = null;
function show(angle) { big.firstChild.textContent = angle === null ? "--" : angle; }
function say(text, bad) { statusEl.textContent = text; statusEl.className = bad ? "bad" : ""; }
async function post(path, body) {
  try {
    const r = await fetch(path, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
    const data = await r.json();
    if (r.status === 502) { say("Board not answering: " + data.error, true); return null; }
    if (!r.ok) { say(data.error || "Something went wrong.", true); return null; }
    return data;
  } catch (e) { say("Board not answering: this page cannot reach its server (" + e + ")", true); return null; }
}
function saved(state) {
  document.getElementById("saved-open").textContent = (state.saved ? "saved: " : "default: ") + state.open;
  document.getElementById("saved-closed").textContent = (state.saved ? "saved: " : "default: ") + state.closed;
}
async function refresh(message) {
  try {
    const state = await (await fetch("/state")).json();
    saved(state);
    if (current === null && state.angle !== null) { current = state.angle; slider.value = current; show(current); }
    if (state.error) say("Board not answering: " + state.error, true);
    else if (message) say(message, false);
    else if (state.angle === null) say("Move the slider or press a button to turn the servo.", false);
  } catch (e) { say("Board not answering: this page cannot reach its server (" + e + ")", true); }
}
async function turn(degrees) {
  degrees = Math.max(0, Math.min(180, degrees));
  slider.value = degrees; show(degrees);
  const data = await post("/angle", {degrees});
  if (data) { current = data.angle; slider.value = current; show(current); say("Turned the servo to " + current + " degrees.", false); }
}
slider.addEventListener("input", () => show(Number(slider.value)));  // only the number while dragging
slider.addEventListener("change", () => turn(Number(slider.value)));  // the servo follows on release
document.querySelectorAll("[data-step]").forEach(b => b.addEventListener("click",
  () => turn((current === null ? Number(slider.value) : current) + Number(b.dataset.step))));
async function save(which) {
  const data = await post("/save", {which});
  if (data) { await refresh("Saved " + data[which] + " degrees as " + which.toUpperCase() + "."); }
}
document.getElementById("save-open").addEventListener("click", () => save("open"));
document.getElementById("save-closed").addEventListener("click", () => save("closed"));
async function testLatch(closed) {
  const data = await post("/test", {closed});
  if (data) say("Test: the latch " + (closed ? "closed" : "opened") + " with the saved angles. The sketch reopens a test close by itself after 30 s.", false);
}
document.getElementById("test-open").addEventListener("click", () => testLatch(false));
document.getElementById("test-close").addEventListener("click", () => testLatch(true));
refresh();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    sys.exit(main())
