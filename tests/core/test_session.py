"""Ephemeral session store (HC-4, roadmap 4.1): TTL, destruction, isolation, turn serialisation."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
import yaml

from slrag.core.session import SessionCapacityError, SessionStore
from slrag.synth.engine import SynthesisEngine, TurnInput
from tests.helpers import scenario_turns, turn_decisions, turn_evidence, turn_sub_intents

APP_CONFIG = Path(__file__).resolve().parents[2] / "config" / "app.yaml"


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class Session:
    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.state: list[str] = []
        self.destroyed = False

    def destroy(self) -> None:
        self.destroyed = True
        self.state.clear()


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def store(clock) -> SessionStore[Session]:
    return SessionStore(Session, ttl_s=60, clock=clock)


def test_sessions_are_created_lazily_and_isolated(store):
    a = store.get("a")
    a.state.append("claim")
    assert store.get("a") is a
    assert store.get("b").state == [] and len(store) == 2


def test_idle_sessions_expire_after_ttl(store, clock):
    a = store.get("a")
    clock.now = 59
    store.get("b")
    assert "a" in store                                  # touched at 0, idle 59 < 60
    clock.now = 61
    assert store.sweep() == ["a"] and a.destroyed
    fresh = store.get("a")
    assert fresh is not a and fresh.state == []


def test_access_renews_the_ttl(store, clock):
    a = store.get("a")
    for clock.now in (50, 100, 150):
        assert store.get("a") is a
    assert not a.destroyed


def test_expiry_is_swept_lazily_on_any_access(store, clock):
    a = store.get("a")
    clock.now = 120
    store.get("other")
    assert a.destroyed and "a" not in store


async def test_a_session_mid_turn_is_never_expired(store, clock):
    async with store.turn("a") as a:
        clock.now = 1000
        assert store.sweep() == [] and not a.destroyed
    clock.now = 1030                                      # the turn's end counts as use
    assert store.sweep() == []
    clock.now = 1061
    assert store.sweep() == ["a"] and a.destroyed


async def test_turns_are_serialised_per_session_and_concurrent_across_sessions(store):
    log: list[str] = []

    async def turn(session_id: str, label: str, hold: float) -> None:
        async with store.turn(session_id):
            log.append(f"{label}:start")
            await asyncio.sleep(hold)
            log.append(f"{label}:end")

    await asyncio.gather(turn("a", "a1", 0.05), turn("a", "a2", 0.0), turn("b", "b1", 0.0))
    assert log.index("a1:end") < log.index("a2:start")      # same session: strictly one after another
    assert log.index("b1:start") < log.index("a1:end")      # other session: not blocked


async def test_end_during_a_turn_defers_destruction(store):
    async with store.turn("a") as a:
        assert store.end("a") is True
        assert not a.destroyed and "a" not in store
    assert a.destroyed
    assert store.get("a") is not a
    assert store.end("missing") is False


async def test_a_turn_queued_behind_end_runs_on_a_fresh_session(store):
    """Audit N-5: the waiting turn must not run on the session that was just retired."""
    seen = []
    first_entered = asyncio.Event()

    async def first():
        async with store.turn("a") as a:
            first_entered.set()
            await asyncio.sleep(0.01)
            store.end("a")
            seen.append(a)

    async def second():
        await first_entered.wait()
        async with store.turn("a") as a:
            seen.append(a)

    await asyncio.gather(first(), second())
    retired, fresh = seen
    assert retired.destroyed and fresh is not retired and not fresh.destroyed
    assert store.get("a") is fresh


async def test_sweep_forever_reclaims_idle_sessions_without_traffic(clock):
    store = SessionStore(Session, ttl_s=60, clock=clock)
    a = store.get("a")
    clock.now = 61
    sweeper = asyncio.create_task(store.sweep_forever(interval_s=0.001))
    for _ in range(50):
        if a.destroyed:
            break
        await asyncio.sleep(0.001)
    sweeper.cancel()
    assert a.destroyed and "a" not in store
    with pytest.raises(ValueError):
        await store.sweep_forever(interval_s=0)


def test_capacity_evicts_the_least_recently_used_idle_session(clock):
    store = SessionStore(Session, ttl_s=60, max_sessions=2, clock=clock)
    a, b = store.get("a"), store.get("b")
    clock.now = 1
    store.get("a")
    store.get("c")
    assert b.destroyed and not a.destroyed and set(store._entries) == {"a", "c"}


async def test_capacity_error_when_every_session_is_mid_turn(clock):
    store = SessionStore(Session, ttl_s=60, max_sessions=1, clock=clock)
    async with store.turn("a"):
        with pytest.raises(SessionCapacityError):
            store.get("b")


def test_close_destroys_everything(store):
    sessions = [store.get(sid) for sid in "abc"]
    store.close()
    assert len(store) == 0 and all(s.destroyed for s in sessions)


def test_invalid_settings_are_rejected():
    with pytest.raises(ValueError):
        SessionStore(Session, ttl_s=0)
    with pytest.raises(ValueError):
        SessionStore(Session, ttl_s=10, max_sessions=0)


def test_from_app_config():
    config = yaml.safe_load(APP_CONFIG.read_text(encoding="utf-8"))
    store = SessionStore.from_config(Session, config)
    assert store._ttl_s == float(config["session"]["ttl_s"])
    assert store._max_sessions == config["session"]["max_sessions"]


async def test_synthesis_engines_live_and_die_in_the_store(clock):
    store = SessionStore(SynthesisEngine, ttl_s=60, clock=clock)
    turn = scenario_turns("example1_multi_intent")[0]
    async with store.turn("s1") as engine:
        result = await engine.handle_turn(
            TurnInput(turn_id=1, utterance=turn["utterance"], t_s_end=turn["t_s_end"],
                      sub_intents=turn_sub_intents(turn), evidence=turn_evidence(turn),
                      retrieval_events=turn["retrieval_events"], controller_decisions=turn_decisions(turn))
        )
    assert result.output.answer_version == 1 and len(engine.graph) > 0
    assert len(store.get("s2").graph) == 0                                   # cross-session isolation
    clock.now = 61
    store.sweep()
    assert len(engine.graph) == 0 and not engine.graph.known_labels()       # HC-4: destroyed on expiry
