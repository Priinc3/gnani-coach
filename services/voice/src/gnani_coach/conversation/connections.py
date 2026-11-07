"""The connection registry: bounded calls per address and per account.

The transport contract asks for "bounded per user and per address"
resource protection. This module is that bound, and nothing else:

* an **address** bound, checked before the handshake is accepted, so a
  refused client never gets a socket;
* a **user** bound, checked once the caller's token has been verified,
  because a user id is only known then.

The counts are per process. A deployment that runs several worker
processes multiplies the effective bound by the number of workers; the
counters are therefore reported, not hidden.

The OWASP WebSocket Security Cheat Sheet asks for resource limits on
concurrent connections
(<https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html>,
checked 2026-10-20).
"""

from __future__ import annotations

import threading
from collections import defaultdict

from gnani_coach.conversation.config import (
    MAX_CONNECTIONS_PER_ADDRESS,
    MAX_CONNECTIONS_PER_USER,
)


class ConnectionRegistry:
    """The live connections, by address and by account."""

    def __init__(
        self,
        *,
        per_address: int = MAX_CONNECTIONS_PER_ADDRESS,
        per_user: int = MAX_CONNECTIONS_PER_USER,
        per_process: int = 10,
    ) -> None:
        self._per_address = int(per_address)
        self._per_user = int(per_user)
        self._per_process = int(per_process)
        self._by_address: dict[str, int] = defaultdict(int)
        self._by_user: dict[str, int] = defaultdict(int)
        self._lock = threading.Lock()

    def configure(
        self,
        *,
        per_address: int,
        per_user: int,
        per_process: int,
    ) -> None:
        """Apply the configured caps.

        A cap change only affects new reservations; live connections are
        never dropped by a configuration change. The values are read from
        ``SPEAKING_COACH_MAX_CONNECTIONS_*`` at startup.
        """
        with self._lock:
            self._per_address = max(1, int(per_address))
            self._per_user = max(1, int(per_user))
            self._per_process = max(1, int(per_process))

    @property
    def per_address(self) -> int:
        return self._per_address

    @property
    def per_user(self) -> int:
        return self._per_user

    @property
    def per_process(self) -> int:
        return self._per_process

    def reserve_address(self, address: str) -> bool:
        """Reserve one slot for an address. False when any bound is hit."""
        with self._lock:
            if sum(self._by_address.values()) >= self._per_process:
                return False
            if self._by_address[address] >= self._per_address:
                return False
            self._by_address[address] += 1
            return True

    def release_address(self, address: str) -> None:
        with self._lock:
            if self._by_address[address] <= 0:
                return
            self._by_address[address] -= 1
            if self._by_address[address] == 0:
                del self._by_address[address]

    def reserve_user(self, user_id: str) -> bool:
        """Reserve one slot for an account. False when the bound is hit."""
        with self._lock:
            if self._by_user[user_id] >= self._per_user:
                return False
            self._by_user[user_id] += 1
            return True

    def release_user(self, user_id: str) -> None:
        with self._lock:
            if self._by_user[user_id] <= 0:
                return
            self._by_user[user_id] -= 1
            if self._by_user[user_id] == 0:
                del self._by_user[user_id]

    def counts(self) -> dict[str, int]:
        """A content-free view of the live counters."""
        with self._lock:
            return {
                "addresses": len(self._by_address),
                "users": len(self._by_user),
                "connections": sum(self._by_address.values()),
                "perAddress": self._per_address,
                "perUser": self._per_user,
                "perProcess": self._per_process,
            }

    def reset(self) -> None:
        """Forget every live connection. For the test suite only."""
        with self._lock:
            self._by_address.clear()
            self._by_user.clear()


#: The process-wide registry the router uses.
registry = ConnectionRegistry()
