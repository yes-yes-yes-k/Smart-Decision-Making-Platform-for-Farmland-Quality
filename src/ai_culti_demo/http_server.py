from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from .diagnosis import diagnose_county
from .overview import get_county_overview
from .report import build_report_summary
from .runtime import verify_standalone_runtime
from .thematic_models import list_thematic_models, run_thematic_model


class DemoRequestHandler(BaseHTTPRequestHandler):
    def _send(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if parsed.path == "/api/county/overview":
            area_code = query.get("area_code", ["lechang"])[0]
            self._send(get_county_overview(area_code))
            return
        if parsed.path == "/api/runtime/verify":
            self._send(verify_standalone_runtime())
            return
        if parsed.path == "/api/models":
            area_code = query.get("area_code", ["lechang"])[0]
            self._send(list_thematic_models(area_code))
            return
        self._send({"status": "error", "error": {"code": "NOT_FOUND"}}, 404)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/county/diagnose":
            self._send(diagnose_county(self._read_json()))
            return
        if parsed.path == "/api/report/summary":
            self._send(build_report_summary(self._read_json()))
            return
        if parsed.path == "/api/models/run":
            self._send(run_thematic_model(self._read_json()))
            return
        self._send({"status": "error", "error": {"code": "NOT_FOUND"}}, 404)

    def log_message(self, format: str, *args: Any) -> None:
        return


def run(host: str = "127.0.0.1", port: int = 8765) -> None:
    server = HTTPServer((host, port), DemoRequestHandler)
    print(f"Serving ai-culti-demo API at http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run()
