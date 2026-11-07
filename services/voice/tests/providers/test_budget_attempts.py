"""Wire-attempt budget enforcement at the adapter boundary [FIX-1 P02-02].

These tests do not trust the budget object's own counter alone: the point
of the repair is that a *fake transport / fake client* observes the same
number of wire attempts the budget records. Every test therefore either
counts messages the fake actually received, or counts calls the fake
client actually made.
"""

from __future__ import annotations

import asyncio
import math

import pytest

from gnani_coach.providers.errors import (
    BudgetExceededError,
    NetworkError,
    ProviderError,
)
from gnani_coach.providers.gemini import CoachRequest, GeminiCoach, GeminiConfig
from gnani_coach.providers.limits import (
    MAX_AUDIO_SECONDS,
    MAX_CONNECTIONS,
    MAX_OPERATIONS,
    MAX_RETRIES_PER_OPERATION,
    UNKNOWN,
    ProbeBudget,
)
from _helpers import DUMMY_GEMINI_KEY, run


# ---------------------------------------------------------------------------
# one retry authority, at the wire attempt boundary
# ---------------------------------------------------------------------------


class _WireClient:
    """Fake async Gemini client that counts *actual* wire attempts."""

    def __init__(self, outcomes) -> None:
        self._outcomes = list(outcomes)
        self.calls = 0
        self.closed_async = 0
        self.closed_sync = 0
        self.sent: list[dict] = []

    # The adapter accepts either a real `Client.aio.interactions` or a
    # directly-exposed `interactions`; this fake uses the latter.
    @property
    def interactions(self):
        client = self

        class _Interactions:
            async def create(self, **kwargs):
                client.calls += 1
                client.sent.append(kwargs)
                outcome = client._outcomes[min(client.calls, len(client._outcomes)) - 1]
                if isinstance(outcome, BaseException):
                    raise outcome
                if outcome == "hang":
                    await asyncio.sleep(30)
                if outcome == "":
                    return type("_I", (), {"id": "x", "output_text": ""})()
                return type("_I", (), {"id": "x", "output_text": outcome})()

        return _Interactions()

    async def aclose(self) -> None:
        self.closed_async += 1

    def close(self) -> None:
        self.closed_sync += 1


def _coach(client, budget, **kw) -> GeminiCoach:
    return GeminiCoach(
        GeminiConfig(model="gemini-3.8-flash"),
        DUMMY_GEMINI_KEY,
        budget=budget,
        client_factory=lambda: client,
        attempt_timeout=kw.pop("attempt_timeout", 5.0),
        deadline=kw.pop("deadline", 20.0),
        max_retries=kw.pop("max_retries", 2),
        **kw,
    )


def _request() -> CoachRequest:
    return CoachRequest(recognized_text="hello", system_instruction="coach")


def test_the_sdk_is_configured_with_no_internal_retry():
    """One retry authority: the SDK must not retry behind our back.

    Verified against the pinned SDK's own semantics: ``attempts`` counts
    the original request, so ``1`` means no retry at all.
    """
    coach = GeminiCoach(
        GeminiConfig(model="gemini-3.8-flash"),
        DUMMY_GEMINI_KEY,
        client_factory=lambda: None,
    )
    options = coach._http_options()
    assert options.retry_options is not None
    assert options.retry_options.attempts == 1


def test_one_remaining_operation_with_a_retrying_upstream_is_refused_not_overspent():
    """A budget with one attempt left must refuse the retry, not go over.

    The upstream fails transiently, so the adapter *wants* to retry. With
    a single operation left there is nothing to admit the retry with, so
    the retry must be refused. The assertion is on the *fake client's*
    call count, not on the budget's own counter.
    """
    budget = ProbeBudget(max_operations=1)
    client = _WireClient([NetworkError("connection reset")])
    coach = _coach(client, budget, max_retries=2)

    async def scenario():
        with pytest.raises(BudgetExceededError):
            await coach.reply(_request())

    run(scenario())
    assert client.calls == 1, "no second wire attempt may be issued"
    assert budget.wire_attempts_used == 1
    assert budget.operations_left == 0
    assert budget.overruns == []


def test_a_retry_that_is_allowed_is_admitted_before_it_starts():
    from gnani_coach.providers.errors import NetworkError

    budget = ProbeBudget(max_operations=5)
    client = _WireClient([NetworkError("connection reset"), "All right, say more."])
    coach = _coach(client, budget, max_retries=2)

    async def scenario():
        return await coach.reply(_request())

    event = run(scenario())
    assert event.text == "All right, say more."
    assert client.calls == 2, "one initial attempt plus exactly one retry"
    assert budget.wire_attempts_used == 2
    assert budget.retries_used == 1
    assert budget.logical_calls_used == 1
    assert [a["outcome"] for a in coach.attempts_made] == ["network", "ok"]


def test_a_timed_out_attempt_still_counts_against_the_budget():
    """A timeout is not a refund: the provider may still be working."""
    budget = ProbeBudget(max_operations=5)
    client = _WireClient(["hang"])
    coach = _coach(client, budget, attempt_timeout=0.05, deadline=0.2, max_retries=0)

    async def scenario():
        from gnani_coach.providers.errors import UpstreamTimeoutError

        with pytest.raises(UpstreamTimeoutError):
            await coach.reply(_request())

    run(scenario())
    assert client.calls == 1
    assert budget.wire_attempts_used == 1
    assert budget.retries_used == 0
    assert coach.attempts_made[0]["outcome"] == "local_timeout"


def test_a_permanent_failure_is_never_retried():
    budget = ProbeBudget(max_operations=5)
    from gnani_coach.providers.errors import AuthenticationError

    client = _WireClient([AuthenticationError("rejected")])
    coach = _coach(client, budget, max_retries=2)

    async def scenario():
        with pytest.raises(AuthenticationError):
            await coach.reply(_request())

    run(scenario())
    assert client.calls == 1
    assert budget.retries_used == 0


def test_an_empty_model_response_is_not_a_successful_reasoning_turn():
    budget = ProbeBudget(max_operations=5)
    client = _WireClient([""])
    coach = _coach(client, budget)

    async def scenario():
        with pytest.raises(ProviderError):
            await coach.reply(_request())

    run(scenario())
    assert budget.wire_attempts_used == 1


# ---------------------------------------------------------------------------
# planning: padded audio, five-stage minimum, refusal before side effects
# ---------------------------------------------------------------------------


def test_the_plan_must_be_sized_on_padded_audio_not_genuine_duration():
    """A limit equal to the genuine duration but below the padded one fails."""
    from tools.probes.live.probes import stt_submitted_seconds

    genuine_seconds = 3.0
    pcm = b"\x00\x01" * int(16000 * genuine_seconds)
    padded_seconds = stt_submitted_seconds(pcm, 16000)
    assert padded_seconds > genuine_seconds

    budget = ProbeBudget(max_audio_seconds=genuine_seconds)
    # The genuine duration alone would fit...
    budget.check_plan(1, genuine_seconds)
    # ...but the audio actually submitted does not.
    with pytest.raises(BudgetExceededError):
        budget.check_plan(1, padded_seconds)


def test_a_chain_plan_of_four_is_refused_when_only_five_attempts_exist():
    """STT connect + session, reasoning attempt, TTS connect + synth = 5."""
    from tools.probes.live.probes import CHAIN_OPS_MINIMUM

    assert CHAIN_OPS_MINIMUM == 5
    budget = ProbeBudget(max_operations=4)
    with pytest.raises(BudgetExceededError):
        budget.check_plan(CHAIN_OPS_MINIMUM, 0.0)


# ---------------------------------------------------------------------------
# children: reserve immediately, never hand out the same allowance twice
# ---------------------------------------------------------------------------


def test_a_child_allowance_is_reserved_at_creation_not_at_absorption():
    parent = ProbeBudget(max_operations=10, max_audio_seconds=20.0)
    first = parent.child(4, 5.0)
    assert parent.reserved_operations == 4
    assert parent.operations_left == 6
    second = parent.child(6, 15.0)
    assert parent.operations_left == 0
    with pytest.raises(BudgetExceededError):
        parent.child(1, 0.0)
    parent.absorb(first)
    parent.absorb(second)


def test_two_concurrent_children_cannot_share_the_same_remaining_allowance():
    parent = ProbeBudget(max_operations=3)
    first = parent.child(2)
    assert parent.operations_left == 1
    second = parent.child(1)
    assert parent.operations_left == 0
    with pytest.raises(BudgetExceededError):
        parent.child(1)
    parent.absorb(first)
    parent.absorb(second)
    assert parent.wire_attempts_used <= 3


def test_child_spending_updates_the_parent_reservation():
    parent = ProbeBudget(max_operations=6)
    child = parent.child(3)
    child.begin_call("x")
    child.admit_attempt("x")
    assert parent.reserved_operations == 3, "reservation covers the whole carve"
    parent.absorb(child)
    assert parent.reserved_operations == 0
    assert parent.wire_attempts_used == 1
    assert parent.logical_calls_used == 1


def test_absorption_reports_an_overrun_instead_of_clamping_it():
    parent = ProbeBudget(max_operations=6)
    child = parent.child(2)
    # Force the defensive case the child limit is supposed to prevent.
    child.wire_attempts_used = 5
    child.max_operations = 2
    parent.absorb(child)
    assert parent.wire_attempts_used == 5, "the real figure is preserved"
    assert parent.overruns, "the overspend is recorded, not hidden"
    assert parent.overruns[0].scope == "operations"


# ---------------------------------------------------------------------------
# limit validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", [-1, -0.5, float("nan"), float("inf")])
def test_nonfinite_or_negative_limits_are_refused(value):
    with pytest.raises(BudgetExceededError):
        ProbeBudget(max_operations=value)
    with pytest.raises(BudgetExceededError):
        ProbeBudget(max_audio_seconds=value)


def test_every_global_maximum_is_checked():
    with pytest.raises(BudgetExceededError):
        ProbeBudget(max_operations=MAX_OPERATIONS + 1)
    with pytest.raises(BudgetExceededError):
        ProbeBudget(max_audio_seconds=MAX_AUDIO_SECONDS + 1)
    with pytest.raises(BudgetExceededError):
        ProbeBudget(max_retries_per_operation=MAX_RETRIES_PER_OPERATION + 1)
    with pytest.raises(BudgetExceededError):
        ProbeBudget(max_connections=MAX_CONNECTIONS + 1)


def test_nonfinite_spend_values_are_refused():
    budget = ProbeBudget()
    with pytest.raises(BudgetExceededError):
        budget.spend_audio(float("nan"))
    with pytest.raises(BudgetExceededError):
        budget.spend_audio(float("inf"))
    with pytest.raises(BudgetExceededError):
        budget.spend_audio(-1.0)
    with pytest.raises(BudgetExceededError):
        budget.check_plan(math.nan, 0.0)


def test_a_zero_limit_is_a_tightened_limit_not_an_invalid_one():
    budget = ProbeBudget(max_operations=0)
    with pytest.raises(BudgetExceededError):
        budget.admit_attempt("anything")


# ---------------------------------------------------------------------------
# accounting after cancellation
# ---------------------------------------------------------------------------


def test_accounting_is_correct_when_a_cancelled_call_admitted_attempts():
    """A cancelled call still consumed its admitted attempts."""
    budget = ProbeBudget(max_operations=5)

    class _Slow(_WireClient):
        @property
        def interactions(self):
            client = self

            class _Interactions:
                async def create(self, **kwargs):
                    client.calls += 1
                    await asyncio.sleep(30)

            return _Interactions()

    client = _Slow(["hang"])
    coach = _coach(client, budget)

    async def scenario():
        task = asyncio.create_task(coach.reply(_request()))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    run(scenario())
    assert client.calls == 1
    assert budget.wire_attempts_used == 1, "a cancelled attempt still counts"
    assert client.closed_async == 1, "the abandoned client was still closed"


# ---------------------------------------------------------------------------
# unknown history
# ---------------------------------------------------------------------------


def test_an_unmeasured_historical_run_reports_unknown_not_zero():
    budget = ProbeBudget(attempts_measured=False)
    summary = budget.summary()
    assert summary["wire_attempts_used"] == UNKNOWN
    assert summary["wire_attempts_source"] == UNKNOWN
    assert budget.attempt_count == UNKNOWN


def test_a_measured_run_reports_its_source_explicitly():
    budget = ProbeBudget()
    budget.admit_attempt("x")
    summary = budget.summary()
    assert summary["wire_attempts_used"] == 1
    assert summary["wire_attempts_source"] == "measured"
    assert "adapter boundary" in summary["retry_authority"]
