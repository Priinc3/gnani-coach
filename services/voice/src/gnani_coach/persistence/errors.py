"""The errors the persistence layer raises.

They are deliberately few, and each one says exactly what went wrong
without carrying a token, a path, a bucket key or any learner content:
a message names a *field* or a *kind*, never a value.

The HTTP router turns them into the frozen error shape
(:func:`gnani_coach.ports.error_shape.error_payload`).
"""

from __future__ import annotations


class PersistenceError(Exception):
    """The base of the persistence errors."""


class StorageUnavailableError(PersistenceError):
    """The storage backend could not be reached or refused the request.

    The message never carries the request, the response body or a
    credential.
    """


class ConsentRequiredError(PersistenceError):
    """A recording write was refused because consent is not in place.

    Raised when recording retention was never granted, and when it was
    granted and then withdrawn. A withdrawal stops future retention; it
    does not delete what was already retained.
    """


class ContentRejectedError(PersistenceError):
    """A durable record carried something a metrics-only record may not.

    The message names the offending *path*, never its value: the value may
    be the learner's own words.
    """


class RecordingFencedError(PersistenceError):
    """A late write tried to recreate a recording that was deleted.

    The fence is what stops a job that was already in flight from
    resurrecting audio the learner deleted.
    """


class GuestWriteRefusedError(PersistenceError):
    """A guest tried to write. A guest has no history and no audio."""


class RecordingTooLargeError(PersistenceError):
    """A recording is larger than the per-file cap."""


class StorageQuotaExceededError(PersistenceError):
    """A recording would push its owner past the per-user cap."""
