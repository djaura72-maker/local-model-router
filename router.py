#!/usr/bin/env python3
"""Unified OpenAI-compatible /v1 proxy routing across LM Studio and Ollama with failover."""

from __future__ import annotations

import argparse
import http.server
import json
import pathlib
import time
import urllib.error
import urllib.request
from typing import Any

DEFAULT_CONFIG = {
    "port": 4000,
    "backends": [
        {"name": "lmstudio", "base_url": "http://localhost:1234/v1", "priority": 1},
        {"name": "ollama", "base_url": "http://localhost:11434/v1", "priority": 2},
    ],
    "routes": {
        "coding": "deepseek-coder-v2",
        "general": "qwen3.5-9b",
        "reasoning": "mistral-nemo",
    },
}

CODING_KEYWORDS = ("def ", "class ", "function ", "bug", "refactor", "typescript", "python", "sql", "git ")


def select_route(messages: list[dict[str, Any]], requested_model: str, routes: dict[str, str]) -> str:
    if requested_model and requested_model != "auto":
        return requested_model
    joined = " ".join(str(m.get("content", "")).lower() for m in messages)
    if any(kw in joined for kw in CODING_KEYWORDS):
        return routes.get("coding", "auto")
    if len(joined) > 600 or "analyze" in joined or "compare" in joined:
        return routes.get("reasoning", "auto")
    return routes.get("general", "auto")


def forward_json(url: str, payload: dict[str, Any] | None = None, method: str = "POST") -> tuple[int, dict[str, Any]]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


class RouterHandler(http.server.BaseHTTPRequestHandler):
    config: dict[str, Any] = DEFAULT_CONFIG

    def _send_json(self, code: int, body: dict[str, Any]) -> None:
        raw = json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_json(200, {"status": "ok", "backends": len(self.config["backends"])})
            return

        if self.path == "/v1/models":
            models: list[dict[str, Any]] = []
            for backend in sorted(self.config["backends"], key=lambda b: b.get("priority", 99)):
                try:
                    _, payload = forward_json(f"{backend['base_url'].rstrip('/')}/models", method="GET")
                    for item in payload.get("data", []):
                        item["backend"] = backend["name"]
                        models.append(item)
                except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
                    continue
            self._send_json(200, {"object": "list", "data": models})
            return

        self._send_json(404, {"error": "Not found"})

    def do_POST(self) -> None:
        if self.path != "/v1/chat/completions":
            self._send_json(404, {"error": "Unsupported endpoint"})
            return

        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length).decode("utf-8"))
        target_model = select_route(
            body.get("messages", []),
            str(body.get("model", "auto")),
            self.config.get("routes", {}),
        )
        body["model"] = target_model

        errors: list[str] = []
        for backend in sorted(self.config["backends"], key=lambda b: b.get("priority", 99)):
            started = time.perf_counter()
            try:
                status, resp_json = forward_json(
                    f"{backend['base_url'].rstrip('/')}/chat/completions",
                    payload=body,
                    method="POST",
                )
                elapsed = time.perf_counter() - started
                print(f"[router] backend={backend['name']} model={target_model} latency={elapsed:.2f}s")
                self._send_json(status, resp_json)
                return
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                errors.append(f"{backend['name']}: {exc}")

        self._send_json(502, {"error": "All local LLM backends failed", "details": errors})

    def log_message(self, format: str, *args: Any) -> None:
        return


def main() -> int:
    parser = argparse.ArgumentParser(description="Unified /v1 router across LM Studio and Ollama.")
    parser.add_argument("--config", help="Optional path to JSON config file.")
    parser.add_argument("--port", type=int, help="Override listening port (default: 4000).")
    args = parser.parse_args()

    cfg = dict(DEFAULT_CONFIG)
    if args.config:
        cfg.update(json.loads(pathlib.Path(args.config).read_text(encoding="utf-8")))
    if args.port:
        cfg["port"] = args.port

    RouterHandler.config = cfg
    server = http.server.HTTPServer(("localhost", int(cfg["port"])), RouterHandler)
    print(f"local-model-router listening on http://localhost:{cfg['port']}/v1")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
