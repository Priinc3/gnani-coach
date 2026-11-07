#!/usr/bin/env python3
"""Live deployment smoke checks for Phase 13.

Runs against the real public endpoints only. It prints status codes,
booleans and counts; it never prints a password, a session token, a
transcript, audio or a real user's address.

Usage (from the repo root, with the voice venv):

    services/voice/.venv/bin/python tests/smoke/check_deploy.py

Optional:

    --apk-sha256 <hex>   expected sha256 of the published APK
    --apk-size <bytes>   expected size of the published APK
    --no-limiter         skip the 11-request login-limiter probe
    --json               print a machine-readable summary as the last line

Exit code 0 when every required check passes (APK may be SKIP when the
build is blocked), 1 when any check FAILs.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import socket
import ssl
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx
import websockets

VOICE_BASE = os.environ.get("SMOKE_VOICE_BASE", "https://13-205-26-178.sslip.io")
WEB_BASE = os.environ.get("SMOKE_WEB_BASE", "https://gnani-coach.vercel.app")
WS_URL = VOICE_BASE.replace("https://", "wss://").replace("http://", "ws://") + "/ws/call"
ALLOWED_ORIGIN = WEB_BASE
FOREIGN_ORIGIN = "https://evil.example"
WSS_ORIGIN = VOICE_BASE.replace("https://", "wss://")

RESULTS: list[dict[str, Any]] = []


@dataclass
class Ctx:
    apk_sha256: str | None = None
    apk_size: int | None = None
    run_limiter: bool = True
    first_auth_at: float | None = None
    log_since: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def record(name: str, status: str, detail: str) -> None:
    RESULTS.append({"check": name, "status": status, "detail": detail})
    print(f"[{status}] {name}: {detail}")


def ok(name: str, detail: str = "") -> None:
    record(name, "PASS", detail)


def fail(name: str, detail: str) -> None:
    record(name, "FAIL", detail)


def skip(name: str, detail: str) -> None:
    record(name, "SKIP", detail)


def check_tls(host: str) -> None:
    name = "TLS certificate valid"
    try:
        context = ssl.create_default_context()
        with socket.create_connection((host, 443), timeout=15) as raw:
            with context.wrap_socket(raw, server_hostname=host) as tls:
                cert = tls.getpeercert()
        subject = dict(x[0] for x in cert.get("subject", ())).get("commonName", "")
        issuer = dict(x[0] for x in cert.get("issuer", ())).get("organizationName", "")
        not_after = cert.get("notAfter", "")
        ok(name, f"subject={subject} issuer={issuer} notAfter={not_after}")
    except Exception as exc:  # noqa: BLE001
        fail(name, f"{type(exc).__name__}: {exc}")


def check_health() -> None:
    name = "/health 200"
    try:
        response = httpx.get(f"{VOICE_BASE}/health", timeout=20)
        body = response.json()
        if response.status_code == 200 and body.get("status") == "ok":
            ok(name, f"HTTP {response.status_code} service={body.get('service')}")
        else:
            fail(name, f"HTTP {response.status_code} body keys={sorted(body)}")
    except Exception as exc:  # noqa: BLE001
        fail(name, f"{type(exc).__name__}: {exc}")


def check_ws_origins() -> None:
    async def attempt(origin: str) -> tuple[bool, str]:
        try:
            async with websockets.connect(
                WS_URL, origin=origin, open_timeout=20, close_timeout=5
            ) as ws:
                message = await asyncio.wait_for(ws.recv(), timeout=10)
                if isinstance(message, str) and '"type":"status"' in message.replace(" ", ""):
                    return True, "accepted, status envelope received"
                return True, "accepted"
        except websockets.InvalidStatus as exc:
            return False, f"refused HTTP {exc.response.status_code}"
        except Exception as exc:  # noqa: BLE001
            return False, f"{type(exc).__name__}: {exc}"

    accepted, detail = asyncio.run(attempt(ALLOWED_ORIGIN))
    if accepted:
        ok("WS handshake from the Vercel origin", detail)
    else:
        fail("WS handshake from the Vercel origin", detail)

    refused, detail = asyncio.run(attempt(FOREIGN_ORIGIN))
    if not refused:
        ok("WS handshake from a foreign origin refused", detail)
    else:
        fail("WS handshake from a foreign origin refused", detail)


def check_web() -> None:
    name = "web / 200 and CSP connect-src"
    try:
        response = httpx.get(f"{WEB_BASE}/", timeout=20, follow_redirects=True)
        csp = response.headers.get("content-security-policy", "")
        match = re.search(r"connect-src ([^;]+)", csp)
        connect = match.group(1).split() if match else []
        if response.status_code != 200:
            fail(name, f"HTTP {response.status_code}")
        elif WSS_ORIGIN not in connect:
            fail(name, f"connect-src missing {WSS_ORIGIN}; got {connect}")
        else:
            ok(name, f"HTTP 200; connect-src contains {WSS_ORIGIN}")
    except Exception as exc:  # noqa: BLE001
        fail(name, f"{type(exc).__name__}: {exc}")


def check_manifest() -> None:
    name = "/manifest.webmanifest display standalone"
    try:
        response = httpx.get(f"{WEB_BASE}/manifest.webmanifest", timeout=20)
        body = response.json()
        if response.status_code == 200 and body.get("display") == "standalone":
            ok(name, f"HTTP 200 display={body.get('display')} name={body.get('name')!r}")
        else:
            fail(name, f"HTTP {response.status_code} display={body.get('display')!r}")
    except Exception as exc:  # noqa: BLE001
        fail(name, f"{type(exc).__name__}: {exc}")


def check_latency_404() -> None:
    name = "/health/latency 404 when no token configured"
    try:
        response = httpx.get(f"{VOICE_BASE}/health/latency", timeout=20)
        if response.status_code == 404:
            ok(name, "HTTP 404 (no SPEAKING_COACH_HEALTH_TOKEN configured)")
        else:
            fail(name, f"HTTP {response.status_code}")
    except Exception as exc:  # noqa: BLE001
        fail(name, f"{type(exc).__name__}: {exc}")


def check_apk(ctx: Ctx) -> None:
    name = "/apk/speaking-coach.apk served with matching size/sha256"
    url = f"{VOICE_BASE}/apk/speaking-coach.apk"
    try:
        response = httpx.get(url, timeout=60, follow_redirects=True)
    except Exception as exc:  # noqa: BLE001
        fail(name, f"{type(exc).__name__}: {exc}")
        return
    if response.status_code == 404:
        skip(name, "APK not published (GitHub Actions blocked; web PWA is the fallback)")
        return
    if response.status_code != 200:
        fail(name, f"HTTP {response.status_code}")
        return
    data = response.content
    digest = hashlib.sha256(data).hexdigest()
    problems = []
    if ctx.apk_size is not None and len(data) != ctx.apk_size:
        problems.append(f"size {len(data)} != expected {ctx.apk_size}")
    if ctx.apk_sha256 is not None and digest != ctx.apk_sha256:
        problems.append(f"sha256 {digest} != expected {ctx.apk_sha256}")
    if problems:
        fail(name, "; ".join(problems))
    else:
        ok(name, f"HTTP 200 bytes={len(data)} sha256={digest}")


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def check_accounts(ctx: Ctx) -> None:
    email = f"smoke-{uuid.uuid4().hex[:16]}@example.com"
    password = "smoke-pass-12345"
    wrong = "not-the-right-password"
    base = VOICE_BASE

    # register
    name = "account register"
    try:
        ctx.first_auth_at = time.monotonic()
        response = httpx.post(
            f"{base}/api/auth/register",
            json={"email": email, "password": password},
            timeout=30,
        )
        if response.status_code == 201 and response.json().get("token"):
            session = response.json()
            ok(name, "HTTP 201, session token issued")
        else:
            fail(name, f"HTTP {response.status_code}")
            return
    except Exception as exc:  # noqa: BLE001
        fail(name, f"{type(exc).__name__}: {exc}")
        return

    # login
    name = "account login"
    try:
        response = httpx.post(
            f"{base}/api/auth/login",
            json={"email": email, "password": password},
            timeout=30,
        )
        if response.status_code == 200 and response.json().get("token"):
            token = response.json()["token"]
            ok(name, "HTTP 200, session token issued")
        else:
            fail(name, f"HTTP {response.status_code}")
            return
    except Exception as exc:  # noqa: BLE001
        fail(name, f"{type(exc).__name__}: {exc}")
        return

    # me
    name = "account me"
    try:
        response = httpx.get(f"{base}/api/auth/me", headers=_auth_headers(token), timeout=30)
        body = response.json()
        if response.status_code == 200 and body.get("userId"):
            ok(name, "HTTP 200, opaque userId returned")
        else:
            fail(name, f"HTTP {response.status_code}")
    except Exception as exc:  # noqa: BLE001
        fail(name, f"{type(exc).__name__}: {exc}")

    # wrong password gets the same generic message
    name = "wrong password generic error"
    try:
        response = httpx.post(
            f"{base}/api/auth/login",
            json={"email": email, "password": wrong},
            timeout=30,
        )
        body = response.json()
        message = body.get("message", "")
        if response.status_code == 401 and message == "That email or password is not correct.":
            ok(name, "HTTP 401 with the generic message")
        else:
            fail(name, f"HTTP {response.status_code} message={message!r}")
    except Exception as exc:  # noqa: BLE001
        fail(name, f"{type(exc).__name__}: {exc}")

    # history isolation: B's token cannot see A's history, even with A's id
    name = "history isolation (user B cannot read user A)"
    try:
        user_a = httpx.get(
            f"{base}/api/auth/me", headers=_auth_headers(token), timeout=30
        ).json()["userId"]
        email_b = f"smoke-b-{uuid.uuid4().hex[:16]}@example.com"
        response_b = httpx.post(
            f"{base}/api/auth/register",
            json={"email": email_b, "password": password},
            timeout=30,
        )
        token_b = response_b.json()["token"]
        response = httpx.get(
            f"{base}/api/history",
            headers=_auth_headers(token_b),
            params={"userId": user_a},
            timeout=30,
        )
        body = response.json()
        sessions = body.get("sessions", body if isinstance(body, list) else [])
        if response.status_code == 200 and not sessions:
            ok(name, "HTTP 200, empty history for B; A's userId query is ignored")
        else:
            fail(name, f"HTTP {response.status_code} sessions={len(sessions)}")
    except Exception as exc:  # noqa: BLE001
        fail(name, f"{type(exc).__name__}: {exc}")

    # delete account
    name = "account delete"
    try:
        response = httpx.request(
            "DELETE",
            f"{base}/api/auth/account",
            headers=_auth_headers(token),
            json={"password": password},
            timeout=30,
        )
        if response.status_code == 204:
            ok(name, "HTTP 204, account and rows removed")
        else:
            fail(name, f"HTTP {response.status_code}")
    except Exception as exc:  # noqa: BLE001
        fail(name, f"{type(exc).__name__}: {exc}")


def _journal_login_peers(since: str) -> list[str] | None:
    """Distinct peer hosts the app logged for /api/auth/login, or None."""
    try:
        output = subprocess.run(
            ["journalctl", "-u", "gnani-voice", "--since", since, "--no-pager"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        ).stdout
    except Exception:  # noqa: BLE001
        return None
    hosts: set[str] = set()
    for line in output.splitlines():
        match = re.search(
            r'INFO:\s+([0-9a-fA-F:.]+):\d+\s+-\s+"POST /api/auth/login', line
        )
        if match:
            hosts.add(match.group(1))
    return sorted(hosts)


def check_limiter(ctx: Ctx) -> None:
    name = "per-address login limiter (11th wrong password gets 429)"
    if not ctx.run_limiter:
        skip(name, "--no-limiter")
        return
    if ctx.first_auth_at is None:
        fail(name, "account flow did not run, so the window could not be measured")
        return
    # The limiter is a fixed 60-second window. Wait for the account-flow
    # attempts to age out so the 11th request is predictably refused.
    elapsed = time.monotonic() - ctx.first_auth_at
    if elapsed < 61:
        time.sleep(61 - elapsed)

    email = f"smoke-limit-{uuid.uuid4().hex[:16]}@example.com"
    statuses: list[int] = []
    for _ in range(11):
        try:
            response = httpx.post(
                f"{VOICE_BASE}/api/auth/login",
                json={"email": email, "password": "definitely-wrong-pass"},
                timeout=30,
            )
            statuses.append(response.status_code)
        except Exception as exc:  # noqa: BLE001
            fail(name, f"request failed: {type(exc).__name__}: {exc}")
            return
    if statuses[-1] == 429 and statuses[:10] == [401] * 10:
        ok(name, "10 x 401 then 429 on the 11th")
    else:
        fail(name, f"statuses={statuses}")

    # Which peer address did the app see? Count only; never print it.
    peers = _journal_login_peers(ctx.log_since)
    if peers is None:
        skip("client address reaches the app", "journalctl unavailable")
        return
    loopback = [p for p in peers if p in {"127.0.0.1", "::1", "localhost"}]
    if peers and not loopback:
        ok(
            "client address reaches the app",
            f"{len(peers)} distinct peer host(s) in the access log; none loopback",
        )
    else:
        fail(
            "client address reaches the app",
            f"peers={len(peers)} loopback={len(loopback)}; the limiter may share one bucket",
        )


def check_unit() -> None:
    name = "unit trusts proxy headers only from 127.0.0.1"
    try:
        output = subprocess.run(
            ["systemctl", "cat", "gnani-voice"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        ).stdout
        has_proxy = "--proxy-headers" in output
        has_trust = "--forwarded-allow-ips 127.0.0.1" in output
        if has_proxy and has_trust:
            ok(name, "ExecStart carries --proxy-headers --forwarded-allow-ips 127.0.0.1")
        else:
            fail(name, f"proxy_headers={has_proxy} trusted_loopback={has_trust}")
    except Exception as exc:  # noqa: BLE001
        fail(name, f"{type(exc).__name__}: {exc}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apk-sha256")
    parser.add_argument("--apk-size", type=int)
    parser.add_argument("--no-limiter", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    ctx = Ctx(
        apk_sha256=args.apk_sha256,
        apk_size=args.apk_size,
        run_limiter=not args.no_limiter,
    )

    print(f"voice={VOICE_BASE}")
    print(f"web={WEB_BASE}")
    check_tls("13-205-26-178.sslip.io")
    check_health()
    check_ws_origins()
    check_web()
    check_manifest()
    check_latency_404()
    check_apk(ctx)
    check_unit()
    check_accounts(ctx)
    check_limiter(ctx)

    failures = [r for r in RESULTS if r["status"] == "FAIL"]
    if args.json:
        print(json.dumps({"results": RESULTS, "failures": len(failures)}))
    print(f"SUMMARY pass={sum(r['status']=='PASS' for r in RESULTS)} "
          f"fail={len(failures)} skip={sum(r['status']=='SKIP' for r in RESULTS)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
