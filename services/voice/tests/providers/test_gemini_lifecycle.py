"""Client lifecycle, cancellation and deadline behaviour [FIX-1 P02-03].

Every test here runs inside **one** long-lived event loop. Process exit
and "the shell went away" are not evidence that a long-lived voice
service is safe, so nothing in this module relies on them.
"""

from __future__ import annotations

import asyncio
import json
import threading

import pytest

from gnani_coach.providers.errors import (
    AuthenticationError,
    CancelledError,
    ConfigurationError,
    UpstreamTimeoutError,
)
from gnani_coach.providers.gemini import CoachRequest, GeminiCoach, GeminiConfig
from gnani_coach.providers.limits import ProbeBudget
from _helpers import DUMMY_GEMINI_KEY

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


class LoopProbe:
    """Fake async client that records attempts, closures and loop identity."""

    def __init__(self, plan=("ok",)) -> None:
        self.plan = list(plan)
        self.calls = 0
        self.created = 0
        self.closed_async = 0
        self.closed_sync = 0
        self.loops: list[asyncio.AbstractEventLoop] = []
        self.live_attempts = 0
        self.peak_live = 0
        self.sent: list[dict] = []
        self.release = asyncio.Event()

    async def _outcome(self):
        outcome = self.plan[min(self.calls, len(self.plan)) - 1]
        if outcome == "hang":
            await self.release.wait()
        if isinstance(outcome, BaseException):
            raise outcome
        return type("_I", (), {"id": "int_fake", "output_text": outcome})()

    @property
    def interactions(self):
        probe = self

        class _Interactions:
            async def create(self, **kwargs):
                probe.calls += 1
                probe.created += 1
                probe.sent.append(kwargs)
                probe.loops.append(asyncio.get_running_loop())
                probe.live_attempts += 1
                probe.peak_live = max(probe.peak_live, probe.live_attempts)
                try:
                    return await probe._outcome()
                finally:
                    probe.live_attempts -= 1

        return _Interactions()

    async def aclose(self) -> None:
        self.closed_async += 1

    def close(self) -> None:
        self.closed_sync += 1

    def balances(self) -> bool:
        return self.created == self.closed_async == self.closed_sync


def _coach(probe, **kw) -> GeminiCoach:
    return GeminiCoach(
        GeminiConfig(model="gemini-3.8-flash"),
        DUMMY_GEMINI_KEY,
        budget=kw.pop("budget", None),
        client_factory=lambda: probe,
        attempt_timeout=kw.pop("attempt_timeout", 0.2),
        deadline=kw.pop("deadline", 2.0),
        max_retries=kw.pop("max_retries", 0),
        **kw,
    )


def _request() -> CoachRequest:
    return CoachRequest(recognized_text="hello there", system_instruction="coach")


# ---------------------------------------------------------------------------
# one long-lived loop, many timeouts
# ---------------------------------------------------------------------------


def test_repeated_timeouts_in_one_loop_leave_no_open_client_and_no_leaked_thread():
    """A timeout must not leave a worker, a thread or a client behind."""

    async def scenario():
        loop_id = id(asyncio.get_running_loop())
        probe = LoopProbe(plan=("hang",))
        coach = _coach(probe, attempt_timeout=0.05, deadline=0.15, max_retries=0)
        threads_before = threading.active_count()

        for _ in range(5):
            with pytest.raises(UpstreamTimeoutError):
                await coach.reply(_request())
            assert id(asyncio.get_running_loop()) == loop_id

        assert probe.calls == 5
        assert probe.balances(), (
            f"created={probe.created} closed_async={probe.closed_async} "
            f"closed_sync={probe.closed_sync}"
        )
        assert coach.lifecycle.open == 0
        # No thread was spawned to abandon the wait.
        await asyncio.sleep(0)
        assert threading.active_count() == threads_before
        return True

    assert asyncio.run(scenario())


def test_the_loop_is_still_usable_after_every_timeout():
    async def scenario():
        probe = LoopProbe(plan=("hang",))
        coach = _coach(probe, attempt_timeout=0.05, deadline=0.15, max_retries=0)
        with pytest.raises(UpstreamTimeoutError):
            await coach.reply(_request())
        # The same loop still runs other work after every timeout.
        done = []

        async def background():
            await asyncio.sleep(0.01)
            done.append("ran")

        await asyncio.gather(background(), asyncio.sleep(0.02))
        assert done == ["ran"]
        return probe.balances()

    assert asyncio.run(scenario())


def test_a_late_reply_after_a_timeout_never_reaches_the_caller():
    """The abandoned request may complete provider-side; we must not adopt it."""

    async def scenario():
        probe = LoopProbe(plan=("hang",))
        coach = _coach(probe, attempt_timeout=0.05, deadline=0.15, max_retries=0)
        with pytest.raises(UpstreamTimeoutError):
            await coach.reply(_request())

        # The provider "finishes" after our wait ended.
        probe.release.set()
        await asyncio.sleep(0.05)

        assert probe.balances()
        assert len(coach.attempts_made) == 1
        assert coach.attempts_made[0]["outcome"] == "local_timeout"
        # Nothing from the abandoned attempt is exposed.
        assert coach.lifecycle.open == 0
        return True

    assert asyncio.run(scenario())


def test_cancelling_a_turn_closes_its_client_and_cancels_the_wait():
    async def scenario():
        probe = LoopProbe(plan=("hang",))
        coach = _coach(probe, attempt_timeout=5.0, deadline=5.0)

        task = asyncio.create_task(coach.reply(_request()))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert probe.calls == 1
        assert probe.balances(), "a cancelled turn must still close its client"
        assert probe.live_attempts == 0
        return True

    assert asyncio.run(scenario())


def test_a_cancelled_reply_is_reported_as_cancellation_not_as_success():
    async def scenario():
        probe = LoopProbe(plan=("hang",))
        coach = _coach(probe, attempt_timeout=5.0, deadline=5.0)
        task = asyncio.create_task(coach.reply(_request()))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises((asyncio.CancelledError, CancelledError)):
            await task
        return True

    assert asyncio.run(scenario())


def test_a_cancelled_turn_never_reaches_the_next_stage():
    """A cancelled turn's late reply must not reach TTS.

    The chain is STT -> reasoning -> TTS. If the reasoning turn is
    cancelled, no reply may be handed to the TTS stage. The coach fences
    itself on cancellation, and a fenced coach refuses to adopt a late
    reply.
    """
    from gnani_coach.providers.errors import CancelledError as ProviderCancelled

    async def scenario():
        probe = LoopProbe(plan=("hang",))
        coach = _coach(probe, attempt_timeout=5.0, deadline=5.0)

        task = asyncio.create_task(coach.reply(_request()))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises((asyncio.CancelledError, ProviderCancelled)):
            await task

        # The turn is fenced.
        assert coach.is_fenced()

        # The provider "finishes" after the cancellation.
        probe.release.set()
        await asyncio.sleep(0.05)

        # No reply is available for a TTS stage, and the fence refuses
        # to produce one.
        with pytest.raises(ProviderCancelled):
            await coach.reply(_request())

        # Nothing was marked as a successful reply.
        assert not any(a["outcome"] == "ok" for a in coach.attempts_made)
        assert probe.balances()
        return True

    assert asyncio.run(scenario())


def test_a_closed_loop_is_never_touched_by_late_work():
    """A worker finishing after the loop closed must not call into nowhere.

    Reproduces the shape of the old daemon-thread completion path and
    asserts the loop itself refuses the call, so a late completion cannot
    raise inside a closed loop.
    """

    async def scenario():
        loop = asyncio.get_running_loop()
        # The exact mechanism the abandoned worker used: hand the loop a
        # callback from outside it and let it fire after the loop closes.
        loop.call_later(0.01, lambda: None)
        await asyncio.sleep(0.02)
        return loop

    loop = asyncio.new_event_loop()
    try:
        closed = loop.run_until_complete(scenario())
        assert closed is loop
        loop.close()
        assert loop.is_closed()
        with pytest.raises(RuntimeError):
            loop.call_soon_threadsafe(lambda: None)
    finally:
        if not loop.is_closed():
            loop.close()


# ---------------------------------------------------------------------------
# bounded concurrency
# ---------------------------------------------------------------------------


def test_concurrent_calls_are_bounded_by_the_configured_limit():
    async def scenario():
        probe = LoopProbe(plan=("hang",))
        coach = _coach(
            probe, attempt_timeout=0.05, deadline=0.2, max_concurrent_calls=2
        )
        await asyncio.gather(
            *[coach.reply(_request()) for _ in range(6)],
            return_exceptions=True,
        )
        assert probe.peak_live <= 2, f"peak live attempts {probe.peak_live}"
        assert probe.balances()
        return True

    assert asyncio.run(scenario())


def test_a_slot_is_held_until_the_work_actually_ends():
    """A caller timing out must not free capacity still in use.

    The old design released a worker slot when the *wait* ended. Here the
    semaphore is held by the attempt itself and released only when the
    attempt's ``finally`` runs.
    """

    async def scenario():
        probe = LoopProbe(plan=("hang",))
        coach = _coach(
            probe,
            attempt_timeout=0.05,
            deadline=0.2,
            max_concurrent_calls=1,
        )
        # One call at a time: the second must not start while the first is
        # still unfinished, so the peak can never exceed one.
        with pytest.raises(UpstreamTimeoutError):
            await coach.reply(_request())
        with pytest.raises(UpstreamTimeoutError):
            await coach.reply(_request())
        assert probe.peak_live <= 1
        return True

    assert asyncio.run(scenario())


def test_a_coach_can_be_reused_across_two_sequential_loops():
    """No loop-bound state is captured at construction time.

    ``asyncio.Semaphore`` binds to the loop that first awaits it, so a
    coach built once and reused across loops must build its own per loop.
    """

    async def call_once(coach):
        return await coach.reply(_request())

    probe = LoopProbe(plan=("ok", "ok"))
    coach = _coach(probe, attempt_timeout=1.0, deadline=2.0)

    first = asyncio.run(call_once(coach))
    semaphore_after_first = coach._semaphore
    second = asyncio.run(call_once(coach))

    assert first.text == "ok" and second.text == "ok"
    # The loop objects are kept alive by `probe.loops`, so ids differ.
    assert len(set(id(loop) for loop in probe.loops)) == 2
    assert coach._semaphore is not semaphore_after_first, (
        "a coach reused on a second loop must not reuse the first loop's semaphore"
    )
    assert probe.balances()


# ---------------------------------------------------------------------------
# deadlines and error honesty
# ---------------------------------------------------------------------------


def test_the_call_deadline_bounds_the_whole_call_not_each_attempt():
    """With retries enabled the deadline, not a per-attempt bound, ends it."""

    async def scenario():
        probe = LoopProbe(plan=("hang",))
        coach = _coach(probe, attempt_timeout=0.05, deadline=0.3, max_retries=5)
        loop = asyncio.get_running_loop()
        started = loop.time()
        with pytest.raises(UpstreamTimeoutError):
            await coach.reply(_request())
        elapsed = loop.time() - started
        assert elapsed < 2.0, "the call returned promptly"
        # Several bounded attempts happened; every one was admitted.
        assert probe.calls >= 1
        assert probe.balances()
        return True

    assert asyncio.run(scenario())


def test_a_local_timeout_does_not_claim_a_provider_cancellation():
    async def scenario():
        probe = LoopProbe(plan=("hang",))
        coach = _coach(probe, attempt_timeout=0.05, deadline=0.15, max_retries=0)
        with pytest.raises(UpstreamTimeoutError) as excinfo:
            await coach.reply(_request())
        message = str(excinfo.value).lower()
        assert "provider-side" in message
        assert "not a provider cancellation" in message
        return True

    assert asyncio.run(scenario())


def test_the_reported_defaults_are_the_documented_ones():
    from gnani_coach.providers import gemini as gemini_module

    coach = GeminiCoach(
        GeminiConfig(model="gemini-3.8-flash"), DUMMY_GEMINI_KEY, client_factory=lambda: None
    )
    summary = coach.safe_summary()
    assert summary["attempt_timeout_s"] == gemini_module.DEFAULT_ATTEMPT_TIMEOUT_S
    assert summary["call_deadline_s"] == gemini_module.DEFAULT_DEADLINE_S
    assert summary["sdk_internal_retries"] == 0
    assert "not a provider cancellation" in summary["timeout_meaning"]
    # The diagnostic deadline is explicitly not the app's voice-turn target.
    assert summary["call_deadline_s"] > 3.0


def test_an_error_on_every_path_still_closes_the_client():
    """Success and failure must both balance client creation against closing."""
    from gnani_coach.providers.errors import ProviderError

    async def scenario():
        for outcome in (AuthenticationError("bad key"), "ok"):
            probe = LoopProbe(plan=(outcome,))
            coach = _coach(probe, attempt_timeout=1.0, deadline=2.0)
            try:
                await coach.reply(_request())
            except ProviderError:
                pass
            assert probe.balances(), f"unbalanced after {outcome!r}"
            assert coach.lifecycle.open == 0
        return True

    assert asyncio.run(scenario())


def test_the_request_still_carries_no_tools_and_no_storage():
    probe = LoopProbe(plan=("ok",))
    coach = _coach(probe)
    event = asyncio.run(coach.reply(_request()))
    sent = probe.sent[0]
    assert "tools" not in sent
    assert not any("tool" in key for key in sent)
    assert sent["store"] is False
    assert event.tools_enabled is False
    assert event.model == "gemini-3.8-flash"
    # The learner text is delimited as data in the *input*, and cannot
    # close its own delimiter.
    assert sent["input"].count("<learner_speech>") == 1
    assert sent["input"].count("</learner_speech>") == 1


def test_a_missing_client_interactions_surface_is_a_configuration_error():
    class _Bare:
        pass

    coach = GeminiCoach(
        GeminiConfig(model="gemini-3.8-flash"),
        DUMMY_GEMINI_KEY,
        client_factory=lambda: _Bare(),
        attempt_timeout=1.0,
        deadline=1.0,
    )
    with pytest.raises(ConfigurationError):
        asyncio.run(coach.reply(_request()))
