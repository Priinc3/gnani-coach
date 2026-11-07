"""Boot the assembled stack for the Phase 07 browser suite.

What runs:

* the **real** FastAPI voice application, in this process, on ``8017``;
* the **real** Next.js application, started by Playwright on ``3107``;
* a fake Supabase HTTP service (Auth + PostgREST + Storage) on ``8018``;
* this control endpoint on ``8019``, used by the browser suite to inject
  provider faults and to read back the service's own log.

What is injected: the speech, reasoning and analysis **ports** only, at the
two factories the product itself uses (``build_call_providers`` and
``get_analysis``). The runtime, the router, the envelope, the identity
verifier, both Supabase stores and every browser byte are real.

The JWT secret is a test fixture (see ``fake_supabase.py``); nothing here
contacts a live provider, and no credential is read.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from harness import (
    CONTROL_PORT,
    FAKE_SUPABASE_PORT,
    SUPABASE_URL,
    VOICE_PORT,
    configure_environment,
    patch_ports,
)

HERE = Path(__file__).resolve().parent
ARTIFACTS = HERE / ".artifacts"
LOG_PATH = ARTIFACTS / "service.log"


class _ControlHandler(BaseHTTPRequestHandler):
    server_version = "AssembledControl/1.0"

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return

    def _body(self) -> dict[str, object]:
        length = int(self.headers.get("content-length", "0") or "0")
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _send(self, status: int, body: object) -> None:
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/control/health":
            self._send(200, {"ok": True})
            return
        if self.path == "/control/dump":
            from gnani_coach.observability.latency import registry

            try:
                log = LOG_PATH.read_text(encoding="utf-8", errors="replace")
            except FileNotFoundError:
                log = ""
            self._send(
                200,
                {
                    "behaviour": fake_stack.BEHAVIOUR.as_dict(),
                    "supabaseFailures": sorted(database.failures),
                    "latency": registry.snapshot(),
                    "log": log,
                    "logPath": str(LOG_PATH),
                },
            )
            return
        self._send(404, {"message": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/control/fail":
            body = self._body()
            fake_stack.BEHAVIOUR.reset()
            fake_stack.BEHAVIOUR.stt_fail = bool(body.get("stt"))
            stt_mode = body.get("sttMode")
            fake_stack.BEHAVIOUR.stt_mode = (
                str(stt_mode) if stt_mode in {"network", "auth", "throttle"} else None
            )
            fake_stack.BEHAVIOUR.tts_fail = bool(body.get("tts"))
            fake_stack.BEHAVIOUR.tts_fail_after = int(body.get("ttsAfter") or 0)
            mode = body.get("reasoning")
            fake_stack.BEHAVIOUR.reasoning_mode = (
                str(mode) if mode in {"timeout", "malformed"} else None
            )
            self._send(200, {"behaviour": fake_stack.BEHAVIOUR.as_dict()})
            return
        if self.path == "/control/supabase":
            body = self._body()
            with database.lock:
                for name in ("rest", "storage", "auth"):
                    if body.get(name):
                        database.failures.add(name)
                    else:
                        database.failures.discard(name)
            self._send(200, {"failures": sorted(database.failures)})
            return
        if self.path == "/control/logs/clear":
            LOG_PATH.write_text("", encoding="utf-8")
            self._send(200, {"ok": True})
            return
        self._send(404, {"message": "not found"})


def start_control() -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", CONTROL_PORT), _ControlHandler)
    thread = threading.Thread(target=server.serve_forever, name="assembled-control", daemon=True)
    thread.start()
    return server


def configure_logging() -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text("", encoding="utf-8")
    formatter = logging.Formatter("%(levelname)s %(name)s %(message)s")
    handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    # uvicorn's access log carries the request paths (and therefore ids),
    # so only warnings and errors are kept.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def main() -> int:
    global fake_stack, database

    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="boot, print ready, exit")
    args = parser.parse_args()

    configure_environment()
    configure_logging()

    from fake_supabase import FakeDatabase, start_fake_supabase

    database = FakeDatabase()
    supabase = start_fake_supabase(database, port=FAKE_SUPABASE_PORT)
    print(f"fake supabase ready on {SUPABASE_URL}", flush=True)

    fake_stack = patch_ports()

    from gnani_coach.main import app

    control = start_control()
    print(f"control ready on http://127.0.0.1:{CONTROL_PORT}", flush=True)

    import uvicorn

    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=VOICE_PORT,
        log_level="info",
        access_log=False,
        lifespan="on",
    )
    server = uvicorn.Server(config)
    if args.check:
        # A boot check without binding the port: the assembled smoke test
        # uses this to prove the injection imports cleanly.
        print("assembled stack imports cleanly", flush=True)
        control.shutdown()
        supabase.shutdown()
        return 0
    try:
        server.run()
    finally:
        control.shutdown()
        supabase.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
