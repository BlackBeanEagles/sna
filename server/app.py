"""Live pipeline console — stdlib HTTP server with Server-Sent Events.

    python server/app.py --port 8124

No framework: ThreadingHTTPServer plus one SSE endpoint is enough, and it keeps
the project's dependency list to what the analysis itself needs.

    GET  /                     the console UI
    GET  /api/months           months available to run
    POST /api/run              start a run -> {run_id}
    GET  /api/stream?run=<id>  SSE event stream for that run
    POST /api/cancel?run=<id>  stop a run
"""
from __future__ import annotations

import argparse
import json
import time
import sys
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server import runner  # noqa: E402

STATIC = Path(__file__).resolve().parent / "static"


class Handler(BaseHTTPRequestHandler):
    """Thin HTTP layer: validate requests, then delegate analysis to runner.py.

    For a presentation, point here for browser-to-Python communication. The
    server returns HTML, JSON endpoints, and a live event stream; it does not
    calculate the statistical result itself.
    """
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):             # keep the console readable
        if "/api/stream" not in self.path:
            sys.stderr.write("  %s %s\n" % (self.command, self.path))

    # ---------------- helpers ----------------
    def _send(self, code, body: bytes, ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj).encode("utf-8"))

    def _query(self):
        return parse_qs(urlparse(self.path).query)

    # ---------------- routes ----------------
    def do_GET(self):
        # The console is live; /findings serves the saved full-study report.
        # Keeping both routes on one local server makes the demo easy to open.
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            html = (STATIC / "index.html").read_bytes()
            return self._send(200, html, "text/html; charset=utf-8")
        if path == "/findings":
            html = (ROOT / "site" / "index.html").read_bytes()
            return self._send(200, html, "text/html; charset=utf-8")
        if path == "/assets/favicon.svg":
            icon = (ROOT / "site" / "assets" / "favicon.svg").read_bytes()
            return self._send(200, icon, "image/svg+xml")
        if path in ("/assets/chess-network-hero.png",
                    "/assets/chess-diffusion-landscape.png",
                    "/assets/chess-diffusion-walnut.png"):
            image = (ROOT / "site" / "assets" / path.rsplit("/", 1)[1]).read_bytes()
            return self._send(200, image, "image/png")
        if path == "/api/runs":
            return self._json({"runs": runner.list_runs()})
        if path == "/api/months":
            return self._json({"months": runner.MONTHS, "stages":
                               [{"key": k, "label": l} for k, l in runner.STAGES]})
        if path == "/api/stream":
            return self._stream()
        return self._send(404, b"not found", "text/plain")

    def do_POST(self):
        # The Run button reaches /api/run, then the browser subscribes to
        # /api/stream. Board moves go to /api/board for legal-move validation.
        path = urlparse(self.path).path
        if path == "/api/run":
            n = int(self.headers.get("Content-Length") or 0)
            cfg = json.loads(self.rfile.read(n) or b"{}")
            months = {m["id"] for m in runner.MONTHS}
            month = cfg.get("month")
            if month not in months:
                return self._json({"error": "unknown month"}, 400)
            cap = cfg.get("max_games")
            cap = int(cap) if cap else None
            if month == runner.DEMO_MONTH:
                cap = None
                cfg["refresh"] = False
            run = runner.start(month, cap,
                               int(cfg.get("null_reps", 20)),
                               int(cfg.get("window_days", 14)),
                               bool(cfg.get("refresh", False)))
            return self._json({"run_id": run.id})
        if path == "/api/resume":
            rid = (self._query().get("run") or [""])[0]
            run = runner.resume(rid)
            return self._json({"run_id": run.id} if run else
                              {"error": "run cannot be resumed"}, 200 if run else 409)
        if path == "/api/board":
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}")
            sans = body.get("sans") or []
            if not isinstance(sans, list) or len(sans) > 200:
                return self._json({"error": "bad move list"}, 400)
            runner.load_board_data(str(body.get("run_id") or ""))
            state = runner.board_state([str(s) for s in sans], body.get("uci"))
            state["has_data"] = runner.LAST.get("df") is not None
            state["month"] = runner.LAST.get("month")
            return self._json(state)
        if path == "/api/cancel":
            rid = (self._query().get("run") or [""])[0]
            run = runner.get(rid)
            if run:
                run.cancel()
            return self._json({"ok": bool(run)})
        return self._send(404, b"not found", "text/plain")

    # ---------------- SSE ----------------
    def _stream(self):
        """Replay saved JSON events and stream new progress to the browser.

        Event IDs let the browser reconnect without losing a running analysis.
        The worker owns the calculation; this request only reads its log.
        """
        rid = (self._query().get("run") or [""])[0]
        run = runner.get(rid)
        if not run:
            return self._json({"error": "unknown run"}, 404)
        try:
            after = max(0, int(self.headers.get("Last-Event-ID") or
                               (self._query().get("after") or ["0"])[0]))
        except ValueError:
            after = 0

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        try:
            position = 0
            stream = None
            last_ping = time.monotonic()
            while True:
                if stream is None and run.events_path.is_file():
                    stream = run.events_path.open("r", encoding="utf-8")
                mark = stream.tell() if stream is not None else 0
                line = stream.readline() if stream is not None else ""
                if line and not line.endswith("\n"):
                    stream.seek(mark)
                    line = ""
                if line:
                    position += 1
                    if position <= after:
                        continue
                    payload = json.loads(line)
                    self.wfile.write(f"id: {position}\n".encode("ascii"))
                    self.wfile.write(b"data: " + line.encode("utf-8") + b"\n")
                    self.wfile.flush()
                    if payload.get("kind") == "done":
                        self.wfile.write(b"event: end\ndata: {}\n\n")
                        self.wfile.flush()
                        return
                    continue
                if run.manifest_path.is_file():
                    status = runner.current_status(json.loads(run.manifest_path.read_text(encoding="utf-8")))
                    if status != "running" and position >= after:
                        if stream is None:
                            self.wfile.write(b'data: {"kind":"log","msg":"No saved progress for this run. Choose Retry in Recent runs.","level":"warn"}\n\n')
                            self.wfile.write(b'data: {"kind":"done","ok":false}\n\n')
                        elif status == "interrupted":
                            self.wfile.write(b'data: {"kind":"done","ok":false,"interrupted":true}\n\n')
                        self.wfile.write(b"event: end\ndata: {}\n\n")
                        self.wfile.flush()
                        return
                if time.monotonic() - last_ping >= 10:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
                    last_ping = time.monotonic()
                time.sleep(0.35)
        except (BrokenPipeError, ConnectionResetError):
            return
        finally:
            if stream is not None:
                stream.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8124)
    ap.add_argument("--host", default="127.0.0.1")
    a = ap.parse_args()
    srv = ThreadingHTTPServer((a.host, a.port), Handler)
    # ASCII only: the Windows console is cp1252 and raises on arrows/dashes
    print(f"Live pipeline console -> http://localhost:{a.port}")
    print("Press Ctrl+C to stop.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
