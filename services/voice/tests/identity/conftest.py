"""Shared setup for the identity tests.

The test directory goes on ``sys.path`` so a test module can import the
fakes with a plain ``from fake_auth import ...``, the same pattern the
provider tests use. Nothing here reaches the network.
"""

from __future__ import annotations

import sys
from pathlib import Path

_IDENTITY_DIR = Path(__file__).resolve().parent

if str(_IDENTITY_DIR) not in sys.path:
    sys.path.insert(0, str(_IDENTITY_DIR))
