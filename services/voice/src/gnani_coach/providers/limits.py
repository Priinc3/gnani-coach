"""Probe safety budget, enforced at the **wire-attempt boundary**.

These are **safety limits**, not pricing estimates and not permission to
buy credit. They exist so that a mistyped loop cannot turn into an
unbounded spend against a live provider.

Defaults come from BUILD.md:

* at most **40 provider operations** per live invocation;
* at most **300 seconds of submitted STT audio**;
* at most **2 retries** for a single transient operation.

One retry authority
-------------------
The **adapter boundary is the only retry authority** in this codebase.
The installed ``google-genai`` SDK can retry internally
(``HttpRetryOptions.attempts`` is *"Maximum number of attempts, including
the original request"*, verified against the pinned 2.31.0 source and by
constructing a client offline), and an internal retry is invisible to any
caller-side counter. This module therefore configures the SDK with
``attempts=1`` — **no internal retry** — and every retry is performed by
:meth:`GeminiCoach.reply` through :meth:`ProbeBudget.admit_attempt`, so
each wire attempt is admitted by this budget *before it starts*.

Four different quantities, never conflated
-----------------------------------------
============================  ==========================================
Quantity                      Meaning
============================  ==========================================
``logical_calls``             one request the caller asked for
``wire_attempts``             one actual HTTP/WebSocket exchange started
``connections``               one transport established
``retries``                   wire attempts beyond the first of a call
============================  ==========================================

An attempt that times out still consumed an attempt. A timed-out attempt
is never refunded, because the provider may still be working on it.

Unknown history
---------------
Runs recorded before this accounting existed carry **no** wire-attempt
count. They are represented by ``wire_attempts_source = "unknown"`` (see
:attr:`ProbeBudget.attempts_measured`), never by a reconstructed zero.

Rules enforced here
-------------------

* An over-limit plan is refused **before** any call is issued.
* Every wire attempt is admitted individually, immediately before it
  starts (:meth:`admit_attempt`).
* Limits are never silently raised, and every limit is validated as
  finite and nonnegative at construction.
* A child allowance is **reserved from the parent at creation**, so two
  concurrent children can never both be handed the same remaining
  allowance.
* Absorption never clamps: an overrun is reported, not hidden.
"""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass, field

from gnani_coach.providers.errors import BudgetExceededError

#: Global ceilings. A caller may *tighten* a budget; it may never raise one
#: above these values. Every one of them is checked at construction.
MAX_OPERATIONS = 40
MAX_AUDIO_SECONDS = 300.0
MAX_RETRIES_PER_OPERATION = 2
MAX_CONNECTIONS = 40
MAX_OUTPUT_BYTES = 4 * 1024 * 1024
MAX_MESSAGE_BYTES = 1 * 1024 * 1024

#: Reported instead of a number when a run predates wire-attempt
#: accounting. "Unknown" is a value; a fabricated 0 is a lie.
UNKNOWN = "unknown"


def _require_finite_nonnegative(name: str, value: object, *, integral: bool) -> float:
    """Reject NaN, infinity, negatives and wrong types for a limit or spend.

    ``float('nan')`` passes every ``> 0`` comparison in the wrong
    direction and ``float('inf')`` silently disables a ceiling, so both are
    refused at the boundary rather than trusted downstream.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BudgetExceededError(f"{name} must be a number, got {type(value).__name__}")
    number = float(value)
    if math.isnan(number):
        raise BudgetExceededError(f"{name} must be a real number, not NaN")
    if math.isinf(number):
        raise BudgetExceededError(f"{name} must be finite, not infinite")
    if number < 0:
        raise BudgetExceededError(f"{name} must be nonnegative, got {value}")
    if integral and not float(number).is_integer():
        raise BudgetExceededError(f"{name} must be a whole number, got {value}")
    return number


@dataclass
class OverrunRecord:
    """An allowance that was crossed anyway. Recorded, never clamped away."""

    scope: str
    kind: str
    over_by: float

    def to_dict(self) -> dict[str, object]:
        return {"scope": self.scope, "kind": self.kind, "over_by": round(self.over_by, 3)}


@dataclass(frozen=True)
class CallToken:
    """Identity of one logical call.

    Two calls of the same kind are different calls. Only attempts that
    carry the *same* token are attempts of one call, and only the second
    and later ones are retries.
    """

    kind: str
    seq: int = 0


@dataclass
class ProbeBudget:
    """Mutable allowance for one live probe invocation.

    The counters are deliberately separate. Collapsing them is exactly how
    a retry that the SDK performed invisibly became an unreported wire
    attempt in the previous revision.
    """

    max_operations: int = MAX_OPERATIONS
    max_audio_seconds: float = MAX_AUDIO_SECONDS
    max_retries_per_operation: int = MAX_RETRIES_PER_OPERATION
    max_connections: int = MAX_CONNECTIONS

    #: Logical calls the caller asked for.
    logical_calls_used: int = 0
    #: Actual wire attempts admitted. This is the number the 40 cap bounds.
    wire_attempts_used: int = 0
    #: Transports established.
    connections_used: int = 0
    #: Wire attempts beyond the first attempt of their logical call.
    retries_used: int = 0
    #: Submitted STT audio, in seconds of *framed submitted samples*.
    audio_seconds_used: float = 0.0

    per_kind: dict[str, int] = field(default_factory=dict)
    #: Total wire attempts charged against each kind.
    attempts_per_kind: dict[str, int] = field(default_factory=dict)
    #: Retries charged against each ``retry:<kind>`` label.
    retries_per_kind: dict[str, int] = field(default_factory=dict)
    #: Retries already spent by each logical call, keyed by its token.
    _retries_per_call: dict["CallToken", int] = field(
        default_factory=dict, repr=False
    )
    #: Attempts already admitted for each logical call, keyed by its token.
    _attempts_per_call: dict["CallToken", int] = field(
        default_factory=dict, repr=False
    )

    #: Attempts reserved for child budgets that have not been absorbed yet.
    reserved_operations: int = 0
    reserved_audio_seconds: float = 0.0
    #: Honest overspend records. Never clamped, never silently dropped.
    overruns: list[OverrunRecord] = field(default_factory=list)

    #: ``False`` marks a historical run whose real wire-attempt count was
    #: never measured. Such a budget reports ``"unknown"``, never ``0``.
    attempts_measured: bool = True

    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _parent: "ProbeBudget | None" = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        """Validate every limit against the global ceilings.

        Limits may be *tightened* by a caller. They may never be raised:
        ``max_operations = 500`` is rejected here rather than honoured,
        so "never silently increase limits" is enforced by construction
        rather than by convention. A tightened limit of ``0`` is allowed
        (the caller wants a plan refused), and a negative or non-finite
        one is refused.
        """
        operations = _require_finite_nonnegative(
            "max_operations", self.max_operations, integral=True
        )
        audio = _require_finite_nonnegative(
            "max_audio_seconds", self.max_audio_seconds, integral=False
        )
        retries = _require_finite_nonnegative(
            "max_retries_per_operation", self.max_retries_per_operation, integral=True
        )
        connections = _require_finite_nonnegative(
            "max_connections", self.max_connections, integral=True
        )
        if operations > MAX_OPERATIONS:
            raise BudgetExceededError(
                f"max_operations {int(operations)} exceeds the hard limit "
                f"{MAX_OPERATIONS}; limits may only be tightened"
            )
        if audio > MAX_AUDIO_SECONDS:
            raise BudgetExceededError(
                f"max_audio_seconds {audio} exceeds the hard "
                f"limit {MAX_AUDIO_SECONDS}; limits may only be tightened"
            )
        if retries > MAX_RETRIES_PER_OPERATION:
            raise BudgetExceededError(
                f"max_retries_per_operation {int(retries)} exceeds "
                f"the hard limit {MAX_RETRIES_PER_OPERATION}"
            )
        if connections > MAX_CONNECTIONS:
            raise BudgetExceededError(
                f"max_connections {int(connections)} exceeds the hard "
                f"limit {MAX_CONNECTIONS}; limits may only be tightened"
            )
        self.max_operations = int(operations)
        self.max_audio_seconds = audio
        self.max_retries_per_operation = int(retries)
        self.max_connections = int(connections)

    # -- planning -----------------------------------------------------
    @property
    def operations_left(self) -> int:
        """Attempts still available, excluding those reserved by children."""
        return max(
            0,
            self.max_operations - self.wire_attempts_used - self.reserved_operations,
        )

    @property
    def audio_seconds_left(self) -> float:
        return max(
            0.0, round(self.max_audio_seconds - self.audio_seconds_used - self.reserved_audio_seconds, 3)
        )

    @property
    def connections_left(self) -> int:
        return max(0, self.max_connections - self.connections_used)

    def check_plan(self, operations: int, audio_seconds: float = 0.0) -> None:
        """Refuse an over-limit plan *before* any provider call.

        ``operations`` here is a count of **wire attempts** the plan needs.
        Callers planning a full turn must count the actual minimum (five
        operations for STT -> reasoning -> TTS, and more again if retries
        are permitted), not the number of visible stages.
        """
        needed = _require_finite_nonnegative("planned operations", operations, integral=True)
        audio = _require_finite_nonnegative("planned audio seconds", audio_seconds, integral=False)
        if needed > self.max_operations:
            raise BudgetExceededError(
                f"plan needs {int(needed)} operations, limit is {self.max_operations}"
            )
        if audio > self.max_audio_seconds + 1e-6:
            raise BudgetExceededError(
                f"plan needs {audio:.1f}s of STT audio, "
                f"limit is {self.max_audio_seconds:.1f}s"
            )
        if needed > self.operations_left:
            raise BudgetExceededError(
                f"plan needs {int(needed)} operations, only {self.operations_left} remain"
            )
        if audio > self.audio_seconds_left + 1e-6:
            raise BudgetExceededError(
                f"plan needs {audio:.1f}s of audio, "
                f"only {self.audio_seconds_left:.1f}s remain"
            )

    def reserve_plan(self, operations: int, audio_seconds: float = 0.0) -> None:
        """Check a plan and immediately book it."""
        with self._lock:
            self.check_plan(operations, audio_seconds)
            self.wire_attempts_used += int(operations)
            self.audio_seconds_used = round(self.audio_seconds_used + float(audio_seconds), 3)

    # -- spending -----------------------------------------------------
    def begin_call(self, kind: str) -> "CallToken":
        """Register one logical call and return its token.

        The token identifies *this* call, so a second call of the same
        kind is never mistaken for a retry of the first. Spending no
        attempt allowance.
        """
        with self._lock:
            self.logical_calls_used += 1
            self.per_kind[kind] = self.per_kind.get(kind, 0) + 1
            token = CallToken(kind=kind, seq=self.logical_calls_used)
            self._attempts_per_call[token] = 0
            self._retries_per_call[token] = 0
            return token

    def admit_attempt(self, kind: str, *, call: "CallToken | None" = None) -> int:
        """Admit exactly one wire attempt. Returns its 1-based attempt number.

        Must be called immediately **before** the attempt is issued. The
        attempt is counted whether it succeeds, fails or times out: a
        timed-out attempt still reached the provider and may still be
        billed.

        A second and subsequent attempt **of the same logical call** is
        counted as a retry, and is refused once
        ``max_retries_per_operation`` retries have been spent. Two
        separate calls of the same kind are not retries of one another:
        pass the token returned by :meth:`begin_call` to keep them apart.
        """
        with self._lock:
            if call is None:
                # A standalone attempt is its own logical call.
                token = CallToken(kind=kind, seq=0)
                self._attempts_per_call.setdefault(token, 0)
                self._retries_per_call.setdefault(token, 0)
            else:
                token = call
                self._attempts_per_call.setdefault(token, 0)
                self._retries_per_call.setdefault(token, 0)

            attempt_number = self._attempts_per_call[token] + 1
            if attempt_number > 1:
                spent = self._retries_per_call[token]
                if spent >= self.max_retries_per_operation:
                    raise BudgetExceededError(
                        f"retry allowance exhausted for {token.kind} "
                        f"({self.max_retries_per_operation} retries); refusing "
                        f"attempt {attempt_number}"
                    )
                self._retries_per_call[token] = spent + 1
                self.retries_used += 1
                name = f"retry:{token.kind}"
                self.retries_per_kind[name] = self.retries_per_kind.get(name, 0) + 1
            if self.wire_attempts_used >= self.max_operations:
                raise BudgetExceededError(
                    f"operation limit reached ({self.max_operations}); refusing {kind}"
                )
            self.wire_attempts_used += 1
            self._attempts_per_call[token] = attempt_number
            # Attempts are attributed to the *logical call* they belong
            # to, so "gemini:reply: 3" means three wire attempts for one
            # reply, not three separate replies.
            self.attempts_per_kind[token.kind] = (
                self.attempts_per_kind.get(token.kind, 0) + 1
            )
            if self._parent is not None:
                self._parent._consume_reserved_attempt(attempt_number)
            return attempt_number

    def spend_audio(self, seconds: float) -> None:
        """Book submitted STT audio, in seconds of *framed submitted samples*.

        The figure must include the trailing silence appended to close the
        provider's VAD window: it is submitted audio and is charged like
        any other.
        """
        amount = _require_finite_nonnegative("audio seconds", seconds, integral=False)
        if amount == 0.0:
            return
        with self._lock:
            if self.audio_seconds_used + amount > self.max_audio_seconds + 1e-6:
                self.overruns.append(
                    OverrunRecord("audio", "spend_audio", self.audio_seconds_used + amount - self.max_audio_seconds)
                )
                raise BudgetExceededError(
                    f"STT audio budget exhausted "
                    f"({self.audio_seconds_used:.1f}s + {amount:.1f}s > "
                    f"{self.max_audio_seconds:.1f}s)"
                )
            self.audio_seconds_used = round(self.audio_seconds_used + amount, 3)
            if self._parent is not None:
                self._parent._consume_reserved_audio(amount)

    def spend_connection(self) -> None:
        with self._lock:
            if self.connections_used >= self.max_connections:
                self.overruns.append(
                    OverrunRecord("connections", "spend_connection", 1)
                )
                raise BudgetExceededError(
                    f"connection limit reached ({self.max_connections})"
                )
            self.connections_used += 1

    def may_retry(self, retries_already_spent: int) -> bool:
        """True while another retry of the same call is still allowed."""
        return retries_already_spent < self.max_retries_per_operation

    # -- children -----------------------------------------------------
    def child(self, operations: int, audio_seconds: float = 0.0) -> ProbeBudget:
        """Carve a strictly smaller sub-budget, **reserving it immediately**.

        The reservation is what stops two concurrent children from both
        being handed the same remaining allowance. The parent's
        ``operations_left`` drops as soon as the child is created, not
        when the child is absorbed.
        """
        with self._lock:
            needed = _require_finite_nonnegative(
                "child operations", operations, integral=True
            )
            audio = _require_finite_nonnegative(
                "child audio seconds", audio_seconds, integral=False
            )
            if needed > self.operations_left:
                raise BudgetExceededError(
                    f"sub-probe needs {int(needed)} operations, "
                    f"only {self.operations_left} remain"
                )
            if audio > self.audio_seconds_left + 1e-6:
                raise BudgetExceededError(
                    f"sub-probe needs {audio:.1f}s of audio, "
                    f"only {self.audio_seconds_left:.1f}s remain"
                )
            if needed > MAX_OPERATIONS or audio > MAX_AUDIO_SECONDS:
                raise BudgetExceededError(
                    "a child allowance may not exceed the global ceilings"
                )
            self.reserved_operations += int(needed)
            self.reserved_audio_seconds = round(self.reserved_audio_seconds + audio, 3)
        return ProbeBudget(
            max_operations=int(needed),
            max_audio_seconds=round(audio, 3),
            max_retries_per_operation=self.max_retries_per_operation,
            max_connections=self.connections_left,
            _parent=self,
        )

    def absorb(self, child_budget: ProbeBudget) -> None:
        """Release a child's unused reservation and fold in its real usage.

        An overrun is **reported**, never clamped: if the child somehow
        spent more than it was reserved (which the child limit prevents,
        and which is recorded as a defensive check), the parent's counters
        move to the child's real figures and an :class:`OverrunRecord` is
        appended so the overspend is visible in the run summary.
        """
        if child_budget._parent is not self:
            raise BudgetExceededError("absorb() called with a budget from another parent")
        child_attempts = child_budget.wire_attempts_used
        if child_attempts > child_budget.max_operations:
            self.overruns.append(
                OverrunRecord(
                    "operations",
                    "absorb",
                    child_attempts - child_budget.max_operations,
                )
            )
        with self._lock:
            self.reserved_operations = max(0, self.reserved_operations - child_budget.max_operations)
            self.reserved_audio_seconds = max(
                0.0, round(self.reserved_audio_seconds - child_budget.max_audio_seconds, 3)
            )
            self.wire_attempts_used += child_attempts
            self.audio_seconds_used = round(
                self.audio_seconds_used + child_budget.audio_seconds_used, 3
            )
            self.connections_used += child_budget.connections_used
            self.logical_calls_used += child_budget.logical_calls_used
            self.retries_used += child_budget.retries_used
            for name, count in child_budget.per_kind.items():
                self.per_kind[name] = self.per_kind.get(name, 0) + count
            for name, count in child_budget.attempts_per_kind.items():
                self.attempts_per_kind[name] = self.attempts_per_kind.get(name, 0) + count
            for name, count in child_budget.retries_per_kind.items():
                self.retries_per_kind[name] = self.retries_per_kind.get(name, 0) + count
            for name, count in child_budget._retries_per_call.items():
                self._retries_per_call[name] = self._retries_per_call.get(name, 0) + count
            for name, count in child_budget._attempts_per_call.items():
                self._attempts_per_call[name] = self._attempts_per_call.get(name, 0) + count
        if self.wire_attempts_used > self.max_operations:
            self.overruns.append(
                OverrunRecord(
                    "operations",
                    "absorb-total",
                    self.wire_attempts_used - self.max_operations,
                )
            )

    def _consume_reserved_attempt(self, _attempt_number: int) -> None:
        """Parent-side hook: the child already holds the reserved attempt.

        The reservation is released in full by :meth:`absorb`, so nothing
        is decremented here; the hook exists so the linkage between a
        child's attempt and its parent's reservation is explicit.
        """
        return None

    def _consume_reserved_audio(self, _seconds: float) -> None:
        return None

    # -- reporting ----------------------------------------------------
    @property
    def attempt_count(self) -> int | str:
        """Wire attempts, or ``"unknown"`` for an unmeasured historical run."""
        return self.wire_attempts_used if self.attempts_measured else UNKNOWN

    def summary(self) -> dict[str, object]:
        return {
            "wire_attempts_used": self.attempt_count,
            "wire_attempts_limit": self.max_operations,
            "wire_attempts_source": "measured" if self.attempts_measured else UNKNOWN,
            "logical_calls_used": self.logical_calls_used,
            "connections_used": self.connections_used,
            "connections_limit": self.max_connections,
            "retries": self.retries_used,
            "max_retries_per_operation": self.max_retries_per_operation,
            "stt_audio_seconds": round(self.audio_seconds_used, 3),
            "stt_audio_seconds_limit": self.max_audio_seconds,
            "reserved_operations": self.reserved_operations,
            "reserved_audio_seconds": round(self.reserved_audio_seconds, 3),
            "overruns": [record.to_dict() for record in self.overruns],
            "per_kind": dict(sorted(self.per_kind.items())),
            "attempts_per_kind": dict(sorted(self.attempts_per_kind.items())),
            "retries_per_kind": dict(sorted(self.retries_per_kind.items())),
            "retry_authority": (
                "adapter boundary; the SDK is configured with no internal retry"
            ),
        }
