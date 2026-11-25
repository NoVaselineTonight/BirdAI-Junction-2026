#!/usr/bin/env python3
"""Feed switch for the Bird AI demo.

A page on this PC (http://localhost:8091) with two buttons. http://localhost:8091/demo waits for the board and
then opens its demo page (http://localhost:8088, which keep-tunnel.sh forwards from the board). A button tells the Arduino UNO Q, over SSH,
which picture to analyse: the USB webcam, or the recorded feeder footage. The board then restarts its demo
program, which takes about half a minute.

Run:  python3 switch.py          (stop with Ctrl+C)
It answers only on this PC (127.0.0.1). It needs the board's address in BIRDAI_BOARD (for example
root@192.168.1.50) and an SSH key the board accepts (BIRDAI_KEY, default ~/.ssh/id_ed25519).
"""
import json
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BOARD = os.environ.get("BIRDAI_BOARD", "")
KEY = os.path.expanduser(os.environ.get("BIRDAI_KEY", "~/.ssh/id_ed25519"))
PORT = int(os.environ.get("BIRDAI_SWITCH_PORT", "8091"))
CONFIG = "/home/arduino/feeder-standalone/config"
SOURCES = {"camera": "Webcam", "reel": "Feeder footage"}

STATE_CMD = (
    f"grep -m1 '^SOURCE=' {CONFIG} | cut -d= -f2 | cut -d' ' -f1; "
    "curl -s -m 4 http://localhost:8088/api/live | "
    "python3 -c 'import sys,json; print(json.load(sys.stdin).get(\"source\"))' 2>/dev/null || echo starting"
)


def board(command, timeout=30):
    """Runs one command on the board: over Wi-Fi (SSH) first, then over the USB cable (adb). Returns (ok, output)."""
    ways = (["ssh", "-i", KEY, "-o", "ConnectTimeout=4", "-o", "BatchMode=yes", BOARD, command],
            ["adb", "shell", command])
    for argv in ways:
        try:
            done = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            continue
        if done.returncode == 0:
            return True, done.stdout.strip()
    return False, ""


def state():
    ok, out = board(STATE_CMD)
    if not ok:
        return {"reachable": False, "wanted": None, "showing": None, "detail": "cannot reach the board"}
    lines = out.splitlines()
    wanted = lines[0].strip() if lines else None
    running = lines[1].strip() if len(lines) > 1 else "starting"
    # The demo calls recorded footage "recorded" and the webcam "camera".
    showing = {"camera": "camera", "recorded": "reel"}.get(running)
    return {"reachable": True, "wanted": wanted if wanted in SOURCES else None, "showing": showing,
            "detail": "" if showing else "the demo is starting"}


def switch(to):
    return board(f"sed -i 's/^SOURCE=[a-z]*/SOURCE={to}/' {CONFIG} && systemctl restart feeder-census")


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bird AI feed switch</title>
<style>
  :root { color-scheme: light dark; --bg:#f3f5f4; --ink:#16262b; --dim:#55676d; --line:#c9d2d0; --on:#1f6f54; --onink:#fff; }
  @media (prefers-color-scheme: dark) { :root { --bg:#12191b; --ink:#e7eeec; --dim:#9fb0b3; --line:#34444a; --on:#3fa27f; --onink:#06140f; } }
  body { margin:0; min-height:100vh; display:grid; place-items:center; background:var(--bg); color:var(--ink);
         font: 18px/1.4 system-ui, sans-serif; }
  main { width:min(640px, calc(100vw - 32px)); }
  h1 { font-size:1.6rem; margin:0 0 4px; }
  p { margin:0 0 20px; color:var(--dim); }
  .row { display:grid; grid-template-columns:1fr 1fr; gap:16px; }
  button { font:inherit; font-size:1.35rem; font-weight:600; padding:28px 12px; border-radius:12px; cursor:pointer;
           border:2px solid var(--line); background:transparent; color:var(--ink); }
  button.on { background:var(--on); border-color:var(--on); color:var(--onink); }
  button:disabled { opacity:.55; cursor:wait; }
  button:focus-visible { outline:3px solid var(--on); outline-offset:3px; }
  #status { margin-top:20px; min-height:1.5em; font-weight:600; }
  @media (max-width:480px) { .row { grid-template-columns:1fr; } }
</style></head><body><main>
<h1>Bird AI feed switch</h1>
<p>Choose what the Arduino analyses and shows. A change takes about half a minute.</p>
<div class="row">
  <button id="camera" type="button">Webcam</button>
  <button id="reel" type="button">Feeder footage</button>
</div>
<div id="status" role="status" aria-live="polite">Asking the board…</div>
</main>
<script>
const names = {camera: "the webcam", reel: "the recorded feeder footage"};
const buttons = {camera: document.getElementById("camera"), reel: document.getElementById("reel")};
const statusEl = document.getElementById("status");
let busy = false, last = "";
function say(text) { if (text !== last) { statusEl.textContent = text; last = text; } }
function show(s) {
  for (const k in buttons) buttons[k].classList.toggle("on", s.showing === k);
  if (!s.reachable) return say("Cannot reach the board. Is it on the same Wi-Fi?");
  if (!s.showing) return say("Switching to " + (names[s.wanted] || "the new feed") + "… the demo is starting.");
  if (s.wanted && s.wanted !== s.showing)
    return say("Showing " + names[s.showing] + " (asked for " + names[s.wanted] + ", which did not answer).");
  say("Showing " + names[s.showing] + ".");
}
async function poll() {
  try { show(await (await fetch("/state")).json()); } catch (e) { say("This page lost its own server."); }
}
async function choose(to) {
  if (busy) return; busy = true;
  for (const k in buttons) buttons[k].disabled = true;
  say("Switching to " + names[to] + "…");
  try {
    const r = await (await fetch("/switch", {method: "POST", headers: {"Content-Type": "application/json"},
                                              body: JSON.stringify({to})})).json();
    if (!r.ok) say("The board refused: " + r.detail);
  } catch (e) { say("Could not send the change."); }
  for (const k in buttons) buttons[k].disabled = false;
  busy = false; poll();
}
buttons.camera.onclick = () => choose("camera");
buttons.reel.onclick = () => choose("reel");
poll(); setInterval(() => { if (!busy) poll(); }, 3000);
</script></body></html>
"""


WAIT_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bird AI</title>
<style>
  :root { color-scheme: light dark; }
  body { margin:0; min-height:100vh; display:grid; place-items:center; font: 22px/1.4 system-ui, sans-serif;
         background:#f3f5f4; color:#16262b; }
  @media (prefers-color-scheme: dark) { body { background:#12191b; color:#e7eeec; } }
  main { text-align:center; padding:16px; }
  h1 { font-size:2.4rem; margin:0 0 8px; }
</style></head><body><main>
<h1>Bird AI</h1>
<div id="msg" role="status">Waiting for the Arduino. This page opens the demo by itself when the board answers.</div>
</main>
<script>
const demo = "http://localhost:8088/";
async function look() {
  try { await fetch(demo + "api/live", {mode: "no-cors", cache: "no-store"}); location.replace(demo); }
  catch (e) { setTimeout(look, 2000); }
}
look();
</script></body></html>
"""


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, kind):
        data = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _from_this_pc(self):
        """Only localhost:<port> or 127.0.0.1:<port>: a web page that points another name at 127.0.0.1 cannot
        switch the board (DNS rebinding). Answers 403 otherwise."""
        port = self.server.server_address[1]
        if self.headers.get("Host") in (f"localhost:{port}", f"127.0.0.1:{port}"):
            return True
        self._send(403, "forbidden", "text/plain")
        return False

    def do_GET(self):
        if not self._from_this_pc():
            return
        if self.path == "/":
            self._send(200, PAGE, "text/html; charset=utf-8")
        elif self.path == "/demo":
            self._send(200, WAIT_PAGE, "text/html; charset=utf-8")
        elif self.path == "/state":
            self._send(200, json.dumps(state()), "application/json")
        else:
            self._send(404, "not found", "text/plain")

    def do_POST(self):
        if not self._from_this_pc():
            return
        if self.path != "/switch" or self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            return self._send(404, "not found", "text/plain")
        try:
            to = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0")))).get("to")
        except (ValueError, AttributeError):
            to = None
        if to not in SOURCES:
            return self._send(400, json.dumps({"ok": False, "detail": "unknown feed"}), "application/json")
        ok, out = switch(to)
        self._send(200, json.dumps({"ok": ok, "detail": out}), "application/json")

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    if not BOARD:
        sys.exit("set BIRDAI_BOARD to the board's address, e.g. root@192.168.1.50")
    print(f"Bird AI feed switch: http://localhost:{PORT}  (board {BOARD})")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
