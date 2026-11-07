"""Phase 02 probe tooling.

Importing this package performs no inference, opens no socket, captures no
microphone and downloads no model asset. Every live operation requires an
explicit ``--allow-live`` switch on ``tools/probes/run.py``.
"""

from __future__ import annotations

__all__ = ["analysis", "fixtures_gen", "fixtures_io", "live", "offline"]
