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
import queue
import sys
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server import runner  # noqa: E402

STATIC = Path(__file__).resolve().parent / "static"


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):             # keep the console readable
        if "/api/stream" not in self.path:
            sys.stderr.write("  %s %s\n" % (self.command, self.path))

    # ---------------- helpers ----------------
    def _send(self, code, body: bytes, ctype="application/json", extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj).encode("utf-8"))

    def _query(self):
        return parse_qs(urlparse(self.path).query)

    # ---------------- routes ----------------
    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            html = (STATIC / "index.html").read_bytes()
            return self._send(200, html, "text/html; charset=utf-8")
        if path == "/api/months":
            return self._json({"months": runner.MONTHS, "stages":
                               [{"key": k, "label": l} for k, l in runner.STAGES]})
        if path == "/api/stream":
            return self._stream()
        return self._send(404, b"not found", "text/plain")

    def do_POST(self):
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
            run = runner.start(month, cap,
                               int(cfg.get("null_reps", 2)),
                               int(cfg.get("window_days", 14)),
                               bool(cfg.get("refresh", False)))
            return self._json({"run_id": run.id})
        if path == "/api/board":
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}")
            sans = body.get("sans") or []
            if not isinstance(sans, list) or len(sans) > 200:
                return self._json({"error": "bad move list"}, 400)
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
        rid = (self._query().get("run") or [""])[0]
        run = runner.get(rid)
        if not run:
            return self._json({"error": "unknown run"}, 404)

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        try:
            while True:
                try:
                    item = run.q.get(timeout=10)
                except queue.Empty:
                    self.wfile.write(b": keepalive\n\n")   # hold the socket open
                    self.wfile.flush()
                    continue
                if item is None:
                    self.wfile.write(b"event: end\ndata: {}\n\n")
                    self.wfile.flush()
                    return
                payload = json.dumps(item, default=str).encode("utf-8")
                self.wfile.write(b"data: " + payload + b"\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            run.cancel()                                    # viewer closed the tab


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
