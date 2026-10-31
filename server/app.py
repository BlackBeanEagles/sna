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
from __future__ import annotations  # Loads code this file needs for the steps below.

import argparse  # Loads the tool that reads command-line choices.
import json  # Loads JSON tools for saved results and browser messages.
import time  # Loads code this file needs for the steps below.
import sys  # Loads code this file needs for the steps below.
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler  # Loads code this file needs for the steps below.
from pathlib import Path  # Loads Path to find and save project files.
from urllib.parse import urlparse, parse_qs  # Loads code this file needs for the steps below.

ROOT = Path(__file__).resolve().parents[1]  # Saves a value named ROOT so the next lines can use it.
sys.path.insert(0, str(ROOT))  # Runs this instruction as part of the current step.

from server import runner  # noqa: E402

STATIC = Path(__file__).resolve().parent / "static"  # Saves a value named STATIC so the next lines can use it.


class Handler(BaseHTTPRequestHandler):  # Thin HTTP layer: validate requests, then delegate analysis to runner.py.
    """Thin HTTP layer: validate requests, then delegate analysis to runner.py.

    For a presentation, point here for browser-to-Python communication. The
    server returns HTML, JSON endpoints, and a live event stream; it does not
    calculate the statistical result itself.
    """
    protocol_version = "HTTP/1.1"  # Saves a value named protocol_version so the next lines can use it.

    def log_message(self, fmt, *args):             # keep the console readable
        if "/api/stream" not in self.path:  # Runs the next indented steps only when this condition is true.
            sys.stderr.write("  %s %s\n" % (self.command, self.path))  # Runs this instruction as part of the current step.

    # ---------------- helpers ----------------
    def _send(self, code, body: bytes, ctype="application/json"):  # Defines a reusable step; the following indented lines are its body.
        self.send_response(code)  # Runs this instruction as part of the current step.
        self.send_header("Content-Type", ctype)  # Runs this instruction as part of the current step.
        self.send_header("Content-Length", str(len(body)))  # Runs this instruction as part of the current step.
        self.send_header("Cache-Control", "no-store")  # Runs this instruction as part of the current step.
        self.end_headers()  # Runs this instruction as part of the current step.
        self.wfile.write(body)  # Runs this instruction as part of the current step.

    def _json(self, obj, code=200):  # Defines a reusable step; the following indented lines are its body.
        self._send(code, json.dumps(obj).encode("utf-8"))  # Encodes Python values as JSON for saving or sending to the browser.

    def _query(self):  # Defines a reusable step; the following indented lines are its body.
        return parse_qs(urlparse(self.path).query)  # Gives this answer back to the code that called the function.

    # ---------------- routes ----------------
    def do_GET(self):  # Defines a reusable step; the following indented lines are its body.
        # The console is live; /findings serves the saved full-study report.
        # Keeping both routes on one local server makes the demo easy to open.
        path = urlparse(self.path).path  # Saves a value named path so the next lines can use it.
        if path in ("/", "/index.html", "/board-demo"):  # Runs the next indented steps only when this condition is true.
            html = (STATIC / "index.html").read_bytes()  # Saves a value named html so the next lines can use it.
            return self._send(200, html, "text/html; charset=utf-8")  # Gives this answer back to the code that called the function.
        if path == "/findings":  # Runs the next indented steps only when this condition is true.
            html = (ROOT / "site" / "index.html").read_bytes()  # Saves a value named html so the next lines can use it.
            return self._send(200, html, "text/html; charset=utf-8")  # Gives this answer back to the code that called the function.
        if path == "/assets/favicon.svg":  # Runs the next indented steps only when this condition is true.
            icon = (ROOT / "site" / "assets" / "favicon.svg").read_bytes()  # Saves a value named icon so the next lines can use it.
            return self._send(200, icon, "image/svg+xml")  # Gives this answer back to the code that called the function.
        if path in ("/assets/chess-network-hero.png",  # Runs the next indented steps only when this condition is true.
                    "/assets/chess-diffusion-landscape.png",
                    "/assets/chess-diffusion-walnut.png"):
            image = (ROOT / "site" / "assets" / path.rsplit("/", 1)[1]).read_bytes()  # Saves a value named image so the next lines can use it.
            return self._send(200, image, "image/png")  # Gives this answer back to the code that called the function.
        if path == "/api/runs":  # Runs the next indented steps only when this condition is true.
            return self._json({"runs": runner.list_runs()})  # Gives this answer back to the code that called the function.
        if path == "/api/board-demo":  # Runs the next indented steps only when this condition is true.
            return self._json(runner.board_demo_payload())  # Loads saved real games for the board without starting a new analysis.
        if path == "/api/months":  # Runs the next indented steps only when this condition is true.
            return self._json({"months": runner.MONTHS, "stages":  # Gives this answer back to the code that called the function.
                               [{"key": k, "label": l} for k, l in runner.STAGES]})  # Part of the value, collection, or call spanning several lines.
        if path == "/api/stream":  # Runs the next indented steps only when this condition is true.
            return self._stream()  # Gives this answer back to the code that called the function.
        return self._send(404, b"not found", "text/plain")  # Gives this answer back to the code that called the function.

    def do_POST(self):  # Defines a reusable step; the following indented lines are its body.
        # The Run button reaches /api/run, then the browser subscribes to
        # /api/stream. Board moves go to /api/board for legal-move validation.
        path = urlparse(self.path).path  # Saves a value named path so the next lines can use it.
        if path == "/api/run":  # Runs the next indented steps only when this condition is true.
            n = int(self.headers.get("Content-Length") or 0)  # Saves a value named n so the next lines can use it.
            cfg = json.loads(self.rfile.read(n) or b"{}")  # Decodes saved JSON text into Python data.
            months = {m["id"] for m in runner.MONTHS}  # Saves a value named months so the next lines can use it.
            month = cfg.get("month")  # Saves a value named month so the next lines can use it.
            if month not in months:  # Runs the next indented steps only when this condition is true.
                return self._json({"error": "unknown month"}, 400)  # Gives this answer back to the code that called the function.
            cap = cfg.get("max_games")  # Saves a value named cap so the next lines can use it.
            cap = int(cap) if cap else None  # Saves a value named cap so the next lines can use it.
            if month in runner.DEMO_SIZES:  # Runs the next indented steps only when this condition is true.
                cap = None  # Saves a value named cap so the next lines can use it.
                cfg["refresh"] = False  # Stores this value under its player, opening, or field key.
            run = runner.start(month, cap,  # Stores the current analysis run for the next step.
                               int(cfg.get("null_reps", 20)),  # Part of the value, collection, or call spanning several lines.
                               int(cfg.get("window_days", 14)),  # Part of the value, collection, or call spanning several lines.
                               bool(cfg.get("refresh", False)),  # Part of the value, collection, or call spanning several lines.
                               bool(cfg.get("predict", False)))  # Runs this instruction as part of the current step.
            return self._json({"run_id": run.id})  # Gives this answer back to the code that called the function.
        if path == "/api/resume":  # Runs the next indented steps only when this condition is true.
            rid = (self._query().get("run") or [""])[0]  # Saves a value named rid so the next lines can use it.
            run = runner.resume(rid)  # Stores the current analysis run for the next step.
            return self._json({"run_id": run.id} if run else  # Gives this answer back to the code that called the function.
                              {"error": "run cannot be resumed"}, 200 if run else 409)  # Part of the value, collection, or call spanning several lines.
        if path == "/api/board":  # Runs the next indented steps only when this condition is true.
            n = int(self.headers.get("Content-Length") or 0)  # Saves a value named n so the next lines can use it.
            body = json.loads(self.rfile.read(n) or b"{}")  # Decodes saved JSON text into Python data.
            sans = body.get("sans") or []  # Stores the moves written in chess notation for the next step.
            if not isinstance(sans, list) or len(sans) > 200:  # Runs the next indented steps only when this condition is true.
                return self._json({"error": "bad move list"}, 400)  # Gives this answer back to the code that called the function.
            selected_run = str(body.get("run_id") or "")  # Saves a value named selected_run so the next lines can use it.
            has_data = runner.load_board_data(selected_run) if selected_run else False  # Saves a value named has_data so the next lines can use it.
            state = runner.board_state([str(s) for s in sans], body.get("uci"))  # Saves a value named state so the next lines can use it.
            if not has_data:  # Runs the next indented steps only when this condition is true.
                state["opening"] = None  # moves still work before a run is selected
            state["has_data"] = has_data  # Stores this value under its player, opening, or field key.
            state["month"] = runner.LAST.get("month") if has_data else None  # Stores this value under its player, opening, or field key.
            return self._json(state)  # Gives this answer back to the code that called the function.
        if path == "/api/cancel":  # Runs the next indented steps only when this condition is true.
            rid = (self._query().get("run") or [""])[0]  # Saves a value named rid so the next lines can use it.
            run = runner.get(rid)  # Stores the current analysis run for the next step.
            if run:  # Runs the next indented steps only when this condition is true.
                run.cancel()  # Runs this instruction as part of the current step.
            return self._json({"ok": bool(run)})  # Gives this answer back to the code that called the function.
        return self._send(404, b"not found", "text/plain")  # Gives this answer back to the code that called the function.

    # ---------------- SSE ----------------
    def _stream(self):  # Replay saved JSON events and stream new progress to the browser.
        """Replay saved JSON events and stream new progress to the browser.

        Event IDs let the browser reconnect without losing a running analysis.
        The worker owns the calculation; this request only reads its log.
        """
        rid = (self._query().get("run") or [""])[0]  # Saves a value named rid so the next lines can use it.
        run = runner.get(rid)  # Stores the current analysis run for the next step.
        if not run:  # Runs the next indented steps only when this condition is true.
            return self._json({"error": "unknown run"}, 404)  # Gives this answer back to the code that called the function.
        try:  # Starts an operation that may need error handling.
            after = max(0, int(self.headers.get("Last-Event-ID") or  # Saves a value named after so the next lines can use it.
                               (self._query().get("after") or ["0"])[0]))  # Part of the value, collection, or call spanning several lines.
        except ValueError:  # Handles this specific failure without hiding other errors.
            after = 0  # Saves a value named after so the next lines can use it.

        self.send_response(200)  # Runs this instruction as part of the current step.
        self.send_header("Content-Type", "text/event-stream")  # Runs this instruction as part of the current step.
        self.send_header("Cache-Control", "no-cache")  # Runs this instruction as part of the current step.
        self.send_header("Connection", "keep-alive")  # Runs this instruction as part of the current step.
        self.send_header("X-Accel-Buffering", "no")  # Runs this instruction as part of the current step.
        self.end_headers()  # Runs this instruction as part of the current step.

        try:  # Starts an operation that may need error handling.
            position = 0  # Saves a value named position so the next lines can use it.
            stream = None  # Saves a value named stream so the next lines can use it.
            last_ping = time.monotonic()  # Saves a value named last_ping so the next lines can use it.
            while True:  # Repeats the indented block until this condition stops holding.
                if stream is None and run.events_path.is_file():  # Runs the next indented steps only when this condition is true.
                    stream = run.events_path.open("r", encoding="utf-8")  # Saves a value named stream so the next lines can use it.
                mark = stream.tell() if stream is not None else 0  # Saves a value named mark so the next lines can use it.
                line = stream.readline() if stream is not None else ""  # Saves a value named line so the next lines can use it.
                if line and not line.endswith("\n"):  # Runs the next indented steps only when this condition is true.
                    stream.seek(mark)  # Runs this instruction as part of the current step.
                    line = ""  # Saves a value named line so the next lines can use it.
                if line:  # Runs the next indented steps only when this condition is true.
                    position += 1  # Adds this amount to the running total.
                    if position <= after:  # Runs the next indented steps only when this condition is true.
                        continue  # Skips this item and moves to the next loop iteration.
                    payload = json.loads(line)  # Decodes saved JSON text into Python data.
                    self.wfile.write(f"id: {position}\n".encode("ascii"))  # Runs this instruction as part of the current step.
                    self.wfile.write(b"data: " + line.encode("utf-8") + b"\n")  # Runs this instruction as part of the current step.
                    self.wfile.flush()  # Runs this instruction as part of the current step.
                    if payload.get("kind") == "done":  # Runs the next indented steps only when this condition is true.
                        self.wfile.write(b"event: end\ndata: {}\n\n")  # Runs this instruction as part of the current step.
                        self.wfile.flush()  # Runs this instruction as part of the current step.
                        return  # Stops this function here.
                    continue  # Skips this item and moves to the next loop iteration.
                if run.manifest_path.is_file():  # Runs the next indented steps only when this condition is true.
                    status = runner.current_status(json.loads(run.manifest_path.read_text(encoding="utf-8")))  # Decodes saved JSON text into Python data.
                    if status != "running" and position >= after:  # Runs the next indented steps only when this condition is true.
                        if stream is None:  # Runs the next indented steps only when this condition is true.
                            self.wfile.write(b'data: {"kind":"log","msg":"No saved progress for this run. Choose Retry in Recent runs.","level":"warn"}\n\n')  # Runs this instruction as part of the current step.
                            self.wfile.write(b'data: {"kind":"done","ok":false}\n\n')  # Runs this instruction as part of the current step.
                        elif status == "interrupted":  # Runs the next indented steps only when this condition is true.
                            self.wfile.write(b'data: {"kind":"done","ok":false,"interrupted":true}\n\n')  # Runs this instruction as part of the current step.
                        self.wfile.write(b"event: end\ndata: {}\n\n")  # Runs this instruction as part of the current step.
                        self.wfile.flush()  # Runs this instruction as part of the current step.
                        return  # Stops this function here.
                if time.monotonic() - last_ping >= 10:  # Runs the next indented steps only when this condition is true.
                    self.wfile.write(b": keepalive\n\n")  # Runs this instruction as part of the current step.
                    self.wfile.flush()  # Runs this instruction as part of the current step.
                    last_ping = time.monotonic()  # Saves a value named last_ping so the next lines can use it.
                time.sleep(0.35)  # Runs this instruction as part of the current step.
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):  # Handles this specific failure without hiding other errors.
            return  # Stops this function here.
        finally:  # Runs cleanup whether the operation succeeds or fails.
            if stream is not None:  # Runs the next indented steps only when this condition is true.
                stream.close()  # Runs this instruction as part of the current step.


def main():  # Defines a reusable step; the following indented lines are its body.
    ap = argparse.ArgumentParser()  # Saves a value named ap so the next lines can use it.
    ap.add_argument("--port", type=int, default=8124)  # Defines a command-line option for this script.
    ap.add_argument("--host", default="127.0.0.1")  # Defines a command-line option for this script.
    a = ap.parse_args()  # Saves a value named a so the next lines can use it.
    srv = ThreadingHTTPServer((a.host, a.port), Handler)  # Saves a value named srv so the next lines can use it.
    # ASCII only: the Windows console is cp1252 and raises on arrows/dashes
    print(f"Live pipeline console -> http://localhost:{a.port}")  # Prints this reading so a command-line run can be followed.
    print("Press Ctrl+C to stop.")  # Prints this reading so a command-line run can be followed.
    try:  # Starts an operation that may need error handling.
        srv.serve_forever()  # Runs this instruction as part of the current step.
    except KeyboardInterrupt:  # Handles this specific failure without hiding other errors.
        print("\nstopped")  # Prints this reading so a command-line run can be followed.


if __name__ == "__main__":  # Runs the command-line entry point only when this file is executed directly.
    main()  # Runs this instruction as part of the current step.
