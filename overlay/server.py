"""
Lightweight overlay server.
Serves static HTML/CSS/JS and exposes /state reading a JSON file written by the CLI.
"""
from __future__ import annotations

import argparse
import json
import logging
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class OverlayHandler(SimpleHTTPRequestHandler):
    state_path: Path
    static_dir: Path
    context_path: Path
    gamestate_path: Path
    gamestate_log_path: Path

    def log_message(self, format: str, *args) -> None:  # noqa: A003 - silence noisy GET logs
        if "GET /state" in format % args:
            return
        super().log_message(format, *args)

    def do_GET(self):  # noqa: N802
        if self.path.rstrip("/") == "/state":
            self.serve_state()
        elif self.path.rstrip("/") == "/context":
            self.serve_context()
        elif self.path.rstrip("/") == "/gamestate":
            self.serve_gamestate()
        else:
            return super().do_GET()

    def do_OPTIONS(self):  # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path.rstrip("/") == "/context":
            self.receive_context()
        elif parsed.path.rstrip("/") == "/gamestate":
            self.receive_gamestate()
            return
        self.send_response(404)
        self.end_headers()

    def serve_state(self) -> None:
        data = {"mode": "clear", "text": "", "font_size": 30, "ts": 0}
        try:
            if self.state_path.exists():
                raw = self.state_path.read_bytes()
                loaded = json.loads(raw.decode("utf-8", errors="replace"))
                if isinstance(loaded, dict):
                    data.update(loaded)
        except Exception as exc:  # pragma: no cover - best effort
            logger.warning("Failed to read state file: %s", exc)

        body = json.dumps(data).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def serve_context(self) -> None:
        data = {"url": "", "selection": "", "ts": 0}
        try:
            if self.context_path.exists():
                raw = self.context_path.read_bytes()
                loaded = json.loads(raw.decode("utf-8", errors="replace"))
                if isinstance(loaded, dict):
                    data.update(loaded)
        except Exception as exc:  # pragma: no cover
            logger.warning("Failed to read context file: %s", exc)

        body = json.dumps(data).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def receive_context(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b""
        try:
            data = json.loads(raw.decode("utf-8", errors="replace"))
            if not isinstance(data, dict):
                raise ValueError("invalid payload")
            self.context_path.parent.mkdir(parents=True, exist_ok=True)
            self.context_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            self.send_response(204)
        except Exception as exc:  # pragma: no cover
            logger.warning("Failed to write context: %s", exc)
            self.send_response(400)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

    def serve_gamestate(self) -> None:
        data = {}
        try:
            if self.gamestate_path.exists():
                raw = self.gamestate_path.read_bytes()
                loaded = json.loads(raw.decode("utf-8", errors="replace"))
                if isinstance(loaded, dict):
                    data.update(loaded)
        except Exception as exc:  # pragma: no cover
            logger.warning("Failed to read gamestate: %s", exc)

        body = json.dumps(data).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def receive_gamestate(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b""
        try:
            data = json.loads(raw.decode("utf-8", errors="replace"))
            if not isinstance(data, dict):
                raise ValueError("invalid payload")
            self.gamestate_path.parent.mkdir(parents=True, exist_ok=True)
            self.gamestate_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            # append to log
            with self.gamestate_log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(data, ensure_ascii=False) + "\n")
            self.send_response(204)
        except Exception as exc:  # pragma: no cover
            logger.warning("Failed to write gamestate: %s", exc)
            self.send_response(400)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

    def translate_path(self, path: str) -> str:  # serve static from static_dir
        new_path = super().translate_path(path)
        rel = Path(new_path).relative_to(Path.cwd())
        return str(self.static_dir / rel)


def main() -> None:
    parser = argparse.ArgumentParser(description="Overlay server for Leviathan")
    parser.add_argument("--state", default="overlay/state.json", help="Path to state JSON file.")
    parser.add_argument("--context", default="overlay/context.json", help="Path to context JSON file.")
    parser.add_argument("--gamestate", default="overlay/gamestate.json", help="Path to gamestate JSON file.")
    parser.add_argument("--gamestate-log", default="overlay/gamestate.log", help="Path to gamestate log file.")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind.")
    parser.add_argument("--port", type=int, default=5005, help="Port to bind.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    state_path = Path(args.state)
    static_dir = Path(__file__).parent / "static"
    context_path = Path(args.context)
    gamestate_path = Path(args.gamestate)
    gamestate_log_path = Path(args.gamestate_log)
    handler_class = type(
        "OverlayHandler",
        (OverlayHandler,),
        {
            "state_path": state_path,
            "static_dir": static_dir,
            "context_path": context_path,
            "gamestate_path": gamestate_path,
            "gamestate_log_path": gamestate_log_path,
        },
    )

    httpd = HTTPServer((args.host, args.port), handler_class)
    logger.info("Serving overlay at http://%s:%s", args.host, args.port)
    logger.info("State file: %s", state_path.resolve())
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down overlay server.")
        httpd.server_close()


if __name__ == "__main__":
    main()


def start_overlay_server(state_path: str | Path, host: str = "127.0.0.1", port: int = 5005) -> HTTPServer:
    """
    Start the overlay server in a background thread. Returns the server instance.
    """
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    state_path = Path(state_path)
    static_dir = Path(__file__).parent / "static"
    context_path = state_path.parent / "context.json"
    gamestate_path = state_path.parent / "gamestate.json"
    gamestate_log_path = state_path.parent / "gamestate.log"
    handler_class = type(
        "OverlayHandler",
        (OverlayHandler,),
        {
            "state_path": state_path,
            "static_dir": static_dir,
            "context_path": context_path,
            "gamestate_path": gamestate_path,
            "gamestate_log_path": gamestate_log_path,
        },
    )
    httpd = HTTPServer((host, port), handler_class)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    logger.info("Overlay server started at http://%s:%s (state=%s)", host, port, state_path.resolve())
    return httpd
