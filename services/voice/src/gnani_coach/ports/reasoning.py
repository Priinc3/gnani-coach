"""The reasoning port.

The reasoning model holds the conversation and writes the coach's spoken
lines. It never measures anything: measured facts come from the analysis
port, and the coach may explain them but never invent or replace them.

Three rules are part of the port, not of an implementation:

* the model is called **without tools**;
* the conversation is not stored server-side (``store=False``);
* the recognised learner speech is **untrusted input**. It is delimited in
  the prompt so a learner utterance cannot act as an instruction.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ReasoningRequest:
    """One bounded coaching turn."""

    recognized_text: str
    instruction: str
    scenario: str = "everyday"
    level: str = "beginner"
    reply_language: str = "English"


@dataclass(frozen=True)
class ReasoningReply:
    """One reply from the reasoning model."""

    text: str
    model: str
    #: Whether the provider was asked to store the conversation. The
    #: frozen configuration is ``False``.
    stored: bool = False
    #: Whether tools were enabled. Must always be ``False`` here.
    tools_enabled: bool = False


@runtime_checkable
class ReasoningPort(Protocol):
    """The application-facing reasoning boundary."""

    async def reply(self, request: ReasoningRequest) -> ReasoningReply:
        """Produce one coach reply, bounded by the adapter's deadline."""
        ...
