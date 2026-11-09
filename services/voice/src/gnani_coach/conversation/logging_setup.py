"""Logging for the call path, applied once from the router module.

Phase 19. The service root logger is at ``WARNING`` in production, so every
``LOGGER.info`` in the call path (including the Phase 16 ``turn timings``
line) was invisible in the journal. This module gives the
``gnani_coach`` logger family a handler at ``INFO`` by default, without
touching ``main.py``.

Only numbers and opaque ids are ever logged by the call path: this module
changes *where* those lines go, never *what* they contain.
"""

from __future__ import annotations

import logging
import os

#: The one handler this module installs. A second import (tests, reloads)
#: must not add a second copy of every line.
_HANDLER_NAME = "gnani_coach.phase19"
_configured = False


def configure() -> None:
    """Install an INFO handler on the ``gnani_coach`` logger once.

    ``SPEAKING_COACH_LOG_LEVEL`` selects the level (default ``INFO``). The
    handler writes to stderr, which systemd sends to the journal. The root
    logger is not touched, so a host that already configures logging keeps
    its own format.
    """
    global _configured
    if _configured:
        return
    _configured = True

    level_name = os.environ.get("SPEAKING_COACH_LOG_LEVEL", "INFO").strip().upper()
    level = getattr(logging, level_name, logging.INFO)

    logger = logging.getLogger("gnani_coach")
    logger.setLevel(level)
    if any(getattr(handler, "name", None) == _HANDLER_NAME for handler in logger.handlers):
        return
    handler = logging.StreamHandler()
    handler.name = _HANDLER_NAME
    handler.setLevel(level)
    handler.setFormatter(
        logging.Formatter("%(levelname)s %(name)s %(message)s")
    )
    logger.addHandler(handler)
    # A host handler on the root logger would otherwise print the line a
    # second time.
    logger.propagate = False
