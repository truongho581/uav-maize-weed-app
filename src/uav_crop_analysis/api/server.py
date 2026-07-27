"""Small localhost HTTP server for the versioned API application."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import threading
from typing import Any

from uav_crop_analysis.api.application import ApiApplication, MAX_REQUEST_BYTES
from uav_crop_analysis.errors import ConfigurationError


class LocalApiServer:
    def __init__(
        self,
        application: ApiApplication,
        *,
        host: str = "127.0.0.1",
        port: int = 8765,
        allow_remote: bool = False,
    ) -> None:
        if not allow_remote and not _is_loopback(host):
            raise ConfigurationError(
                "REST API may only bind loopback unless allow_remote is explicitly enabled",
                context={"host": host},
            )
        handler = _handler(application)
        self._server = ThreadingHTTPServer((host, port), handler)
        self._thread: threading.Thread | None = None

    @property
    def address(self) -> tuple[str, int]:
        host, port = self._server.server_address[:2]
        return str(host), int(port)

    def serve_forever(self) -> None:
        self._server.serve_forever()

    def start(self) -> tuple[str, int]:
        if self._thread is not None:
            return self.address
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="uav-crop-local-api",
            daemon=True,
        )
        self._thread.start()
        return self.address

    def shutdown(self) -> None:
        if self._thread is not None:
            self._server.shutdown()
            self._thread.join(timeout=5)
            self._thread = None
        self._server.server_close()

    def __enter__(self) -> LocalApiServer:
        self.start()
        return self

    def __exit__(self, *_args: object) -> None:
        self.shutdown()


def _handler(application: ApiApplication) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "UAVCropAnalysisAPI/1"

        def do_GET(self) -> None:
            self._handle()

        def do_POST(self) -> None:
            self._handle()

        def do_PUT(self) -> None:
            self._handle()

        def do_DELETE(self) -> None:
            self._handle()

        def _handle(self) -> None:
            length_text = self.headers.get("Content-Length", "0")
            try:
                length = int(length_text)
            except ValueError:
                self.send_error(400, "invalid Content-Length")
                return
            if length < 0 or length > MAX_REQUEST_BYTES:
                self.send_error(413, "request body too large")
                return
            body = self.rfile.read(length) if length else b""
            response = application.handle(self.command, self.path, body)
            encoded = json.dumps(
                response.payload,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
            self.send_response(response.status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, _format: str, *args: Any) -> None:
            return

    return Handler


def _is_loopback(host: str) -> bool:
    if host.casefold() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False
