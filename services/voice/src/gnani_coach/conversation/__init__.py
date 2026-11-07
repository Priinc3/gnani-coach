"""Conversation runtime — **Phase 05 owns this tree**.

Phase 03 created this package as an empty stub so that the composition
root in ``gnani_coach.main`` can mount the conversation routes and so that
G1 builders have a real import to look at. The stub answers with the
frozen ``not_available`` behaviour; Phase 05 replaces it.

Frozen contract: ``docs/contracts/seams.md`` and
``docs/contracts/call-transport.md``.
"""

from gnani_coach.conversation.router import router

__all__ = ["router"]
