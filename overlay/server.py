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

logger = logging.getLogger(__name__)


class OverlayHandler(SimpleHTTPRequestHandler):
    state_path: Path
    static_dir: Path

    def log_message(self, format: str, *args) -> None:  # noqa: A003 - silence noisy GET logs
        if "GET /state" in format % args:
            return
        super().log_message(format, *args)

    def do_GET(self):  # noqa: N802
        if self.path.rstrip("/") == "/state":
            self.serve_state()
        else:
            return super().do_GET()

    def serve_state(self) -> None:
        data = {"mode": "clear", "text": "", "font_size": 30, "ts": 0}
        try:
            if self.state_path.exists():
                loaded = json.loads(self.state_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    data.update(loaded)
        except Exception as exc:  # pragma: no cover - best effort
            logger.warning("Failed to read state file: %s", exc)

        body = json.dumps(data).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def translate_path(self, path: str) -> str:  # serve static from static_dir
        new_path = super().translate_path(path)
        rel = Path(new_path).relative_to(Path.cwd())
        return str(self.static_dir / rel)


def main() -> None:
    parser = argparse.ArgumentParser(description="Overlay server for Leviathan")
    parser.add_argument("--state", default="overlay/state.json", help="Path to state JSON file.")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind.")
    parser.add_argument("--port", type=int, default=5005, help="Port to bind.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    state_path = Path(args.state)
    static_dir = Path(__file__).parent / "static"
    handler_class = type(
        "OverlayHandler",
        (OverlayHandler,),
        {"state_path": state_path, "static_dir": static_dir},
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
    handler_class = type(
        "OverlayHandler",
        (OverlayHandler,),
        {"state_path": state_path, "static_dir": static_dir},
    )
    httpd = HTTPServer((host, port), handler_class)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    logger.info("Overlay server started at http://%s:%s (state=%s)", host, port, state_path.resolve())
    return httpd
