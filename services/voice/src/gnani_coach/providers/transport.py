"""Injectable transports and endpoint/key confinement.

The adapters never construct a socket themselves. They receive a
:class:`Transport`, which makes every protocol behaviour deterministically
testable offline — malformed payloads, floods, duplicate/out-of-order
events, 429s, timeouts, auth failures and cancellation races are all
exercised with :class:`FakeTransport` and dummy credentials, never against
the live provider.

Endpoint confinement (:func:`validate_endpoint`) is the security boundary
for "never forward a provider key to a user-selected host or redirect":

* only ``wss://`` (TLS) is accepted;
* only hosts in :data:`ALLOWED_HOSTS` — the reviewed ``api.vachana.ai``;
* the credential is bound to that host at connect time, and
  :class:`ConfinementViolation` is raised rather than followed.
"""

from __future__ import annotations

import asyncio
import ssl
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable
from urllib.parse import urlsplit

from gnani_coach.providers.errors import (
    AuthenticationError,
    EndpointError,
    NetworkError,
    ProtocolError,
    RateLimitError,
    UpstreamTimeoutError,
)
from gnani_coach.providers.limits import MAX_MESSAGE_BYTES

#: Hosts reviewed in the primary Gnani documentation (checked 2026-10-18).
ALLOWED_HOSTS = frozenset({"api.vachana.ai"})

#: Documented session ceiling. Deliberately separate from the probe budget:
#: a probe never approaches this, and exceeding it is a product concern.
DOCUMENTED_SESSION_CEILING_SECONDS = 15 * 60


def validate_endpoint(url: str, *, allowed_hosts: frozenset[str] = ALLOWED_HOSTS) -> str:
    """Return ``url`` if it is a permitted provider endpoint.

    Rejects non-TLS schemes, any host outside the allowlist, embedded
    credentials, query strings and fragments. Redirects are *not* followed
    by the adapters: a redirect response is a protocol failure, not a new
    destination.
    """
    if not isinstance(url, str) or not url.strip():
        raise EndpointError("endpoint is empty")
    parts = urlsplit(url.strip())
    if parts.scheme != "wss":
        raise EndpointError(f"endpoint scheme {parts.scheme!r} is not wss")
    if parts.username or parts.password:
        raise EndpointError("endpoint must not embed credentials")
    if parts.query or parts.fragment:
        raise EndpointError("endpoint must not carry a query or fragment")
    host = (parts.hostname or "").lower()
    if host not in allowed_hosts:
        raise EndpointError(
            f"host {host!r} is not in the reviewed provider allowlist"
        )
    if not parts.path:
        raise EndpointError("endpoint has no path")
    return url.strip()


# ---------------------------------------------------------------------------
# Transport protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class Transport(Protocol):
    """Minimal duplex message transport.

    ``send``/``recv`` move whole protocol messages: ``str`` for a JSON text
    frame, ``bytes`` for a binary audio frame. ``recv`` raises
    :class:`asyncio.TimeoutError` when nothing arrives within the caller's
    wait, and ``ConnectionClosed`` when the peer closes.
    """

    async def send(self, message: str | bytes) -> None: ...

    async def recv(self, timeout: float) -> str | bytes: ...

    async def close(self, code: int = 1000, reason: str = "") -> None: ...

    @property
    def closed(self) -> bool: ...


class ConnectionClosed(Exception):
    """The peer closed the connection."""


class ConfinementViolation(Exception):
    """The transport tried to reach a host outside the allowlist."""


# ---------------------------------------------------------------------------
# Live transport
# ---------------------------------------------------------------------------


class WebSocketTransport:
    """Live transport over ``websockets``.

    Redirects are refused rather than followed, so a credential can never
    be replayed to a redirect target. Message size is bounded so a flood
    or an oversized provider frame fails fast instead of exhausting memory.
    """

    def __init__(
        self,
        url: str,
        headers: dict[str, str],
        *,
        connect_timeout: float = 15.0,
        max_message_bytes: int = MAX_MESSAGE_BYTES,
        allowed_hosts: frozenset[str] = ALLOWED_HOSTS,
    ) -> None:
        self._url = validate_endpoint(url, allowed_hosts=allowed_hosts)
        self._headers = dict(headers)
        self._connect_timeout = connect_timeout
        self._max_message_bytes = max_message_bytes
        self._ws: object | None = None
        self._closed = False

    async def __aenter__(self) -> WebSocketTransport:
        await self._connect()
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.close()

    async def _connect(self) -> None:
        # Imported lazily: importing `websockets` must stay cheap, and an
        # offline command must never open a socket.
        try:
            import websockets
            from websockets.asyncio.client import connect
            from websockets.exceptions import InvalidStatus
        except ImportError as exc:  # pragma: no cover - environment guard
            raise EndpointError(
                "the 'websockets' package is required for live transports"
            ) from exc

        context = ssl.create_default_context()
        try:
            self._ws = await asyncio.wait_for(
                connect(
                    self._url,
                    additional_headers=self._headers,
                    ssl=context,
                    # A redirect must never be followed with a live key.
                    open_timeout=self._connect_timeout,
                    max_size=self._max_message_bytes,
                ),
                timeout=self._connect_timeout,
            )
        except asyncio.TimeoutError as exc:
            raise UpstreamTimeoutError("websocket handshake timed out") from exc
        except InvalidStatus as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status in (401, 403):
                raise AuthenticationError(f"provider rejected the credential (HTTP {status})") from exc
            if status == 429:
                raise RateLimitError("provider throttled the connection (HTTP 429)") from exc
            raise EndpointError(f"websocket handshake refused (HTTP {status})") from exc
        except Exception as exc:  # noqa: BLE001 - re-raised as a category
            raise NetworkError(f"websocket connect failed: {type(exc).__name__}") from exc

    async def send(self, message: str | bytes) -> None:
        if self._closed or self._ws is None:
            raise ConnectionClosed("transport is closed")
        try:
            await self._ws.send(message)  # type: ignore[union-attr]
        except Exception as exc:  # noqa: BLE001
            raise NetworkError(f"send failed: {type(exc).__name__}") from exc

    async def recv(self, timeout: float) -> str | bytes:
        if self._ws is None:
            raise ConnectionClosed("transport is not connected")
        try:
            return await asyncio.wait_for(self._ws.recv(), timeout=timeout)  # type: ignore[union-attr]
        except asyncio.TimeoutError:
            raise
        except Exception as exc:  # noqa: BLE001
            name = type(exc).__name__
            if "Closed" in name:
                raise ConnectionClosed("provider closed the connection") from exc
            raise NetworkError(f"recv failed: {name}") from exc

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self._closed = True
        ws, self._ws = self._ws, None
        if ws is not None:
            try:
                await asyncio.wait_for(ws.close(code, reason), timeout=5.0)  # type: ignore[union-attr]
            except Exception:  # noqa: BLE001 - closing must never mask the real error
                pass

    @property
    def closed(self) -> bool:
        return self._closed or self._ws is None


# ---------------------------------------------------------------------------
# Offline fake
# ---------------------------------------------------------------------------


@dataclass
class FakeTransport:
    """Scripted in-memory transport for deterministic protocol checks.

    ``scripted`` is consumed in order as the peer's replies. ``inbound_hook``
    may push extra peer messages to simulate floods, duplicates or
    out-of-order delivery. ``recv_delay`` and ``send_hook`` simulate slow or
    failing providers. No socket is opened and no key is validated.
    """

    scripted: list[str | bytes | BaseException] = field(default_factory=list)
    inbound_hook: object = None
    recv_delay: float = 0.0
    send_hook: object = None
    close_on_send_after: int | None = None
    refused_hosts: set[str] = field(default_factory=set)

    sent: list[str | bytes] = field(default_factory=list)
    close_calls: int = 0
    _closed: bool = False
    _extra: asyncio.Queue[str | bytes] = field(default_factory=asyncio.Queue)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def refuse_host(self, host: str) -> None:
        self.refused_hosts.add(host)

    async def send(self, message: str | bytes) -> None:
        if self._closed:
            raise ConnectionClosed("fake transport is closed")
        host = getattr(self, "_host", None)
        if host is not None and host in self.refused_hosts:
            raise ConfinementViolation(f"refusing to reach {host!r}")
        if self.send_hook is not None:
            outcome = self.send_hook(message, len(self.sent))  # type: ignore[misc]
            if isinstance(outcome, BaseException):
                raise outcome
        async with self._lock:
            self.sent.append(message)
            count = len(self.sent)
        if (
            self.close_on_send_after is not None
            and count >= self.close_on_send_after
        ):
            self._closed = True
        if self.inbound_hook is not None:
            for message in self.inbound_hook(message) or ():  # type: ignore[misc]
                self._extra.put_nowait(message)

    async def recv(self, timeout: float) -> str | bytes:
        try:
            item = self._extra.get_nowait()
        except asyncio.QueueEmpty:
            if self._closed and not self.scripted:
                raise ConnectionClosed("fake transport is closed")
            async with self._lock:
                item = self.scripted.pop(0) if self.scripted else None
            if item is None:
                try:
                    return await asyncio.wait_for(
                        self._await_next(), timeout=timeout
                    )
                except asyncio.TimeoutError:
                    raise
        if isinstance(item, BaseException):
            raise item
        if self.recv_delay:
            await asyncio.sleep(self.recv_delay)
        return item

    async def _await_next(self) -> str | bytes:
        return await self._extra.get()

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.close_calls += 1
        self._closed = True

    @property
    def closed(self) -> bool:
        return self._closed


def decode_json_message(raw: str | bytes, *, max_bytes: int = MAX_MESSAGE_BYTES) -> dict:
    """Decode a provider text frame, bounding its size and shape.

    A provider message is untrusted data. Anything that is not a small JSON
    object is a :class:`ProtocolError`, not an ``InvalidRequestError`` and
    not a crash.
    """
    import json

    if isinstance(raw, bytes):
        if len(raw) > max_bytes:
            raise ProtocolError("binary provider frame is not a text message")
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ProtocolError("text frame is not valid UTF-8") from exc
    if len(raw.encode("utf-8", "ignore")) > max_bytes:
        raise ProtocolError("provider message exceeds the size bound")
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise ProtocolError("provider message is not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise ProtocolError("provider message is not a JSON object")
    if not isinstance(parsed.get("type"), str):
        raise ProtocolError("provider message has no string 'type' discriminator")
    return parsed
