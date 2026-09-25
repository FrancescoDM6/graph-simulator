"""Causal trails: every event's `caused_by` points at earlier events that make sense."""

from functools import cache

from graphsim import engine
from graphsim.config import load_scenario
from graphsim.model import TrustChange, World
from graphsim.world_gen import build_world

TICKS = 400  # includes the first drought (ticks 200-259)


@cache
def run() -> tuple[World, tuple[TrustChange, ...]]:
    world = build_world(load_scenario().config(), seed=1)
    ledger: list[TrustChange] = []
    for _ in range(TICKS):
        engine.step(world)
        ledger.extend(world.trust_changes)
    return world, tuple(ledger)


def test_causes_exist_and_come_before_their_effects():
    world, _ = run()
    for event in world.log.events:
        for cause_id in event.caused_by:
            cause = world.log.get(cause_id)
            assert cause_id < event.id
            assert cause.tick <= event.tick


def test_trust_crossings_point_at_an_interaction_between_the_same_pair():
    world, _ = run()
    crossings = [e for e in world.log.events if e.kind in ("trusted", "distrusted")]
    assert crossings
    for event in crossings:
        (cause_id,) = event.caused_by
        interaction = world.log.get(cause_id)
        assert interaction.kind in ("trade", "gift", "refused")
        assert set(event.subjects) <= set(interaction.subjects)


def test_every_trust_change_is_in_the_ledger_with_its_interaction():
    world, ledger = run()
    assert ledger
    for change in ledger:
        interaction = world.log.get(change.event_id)
        assert {change.a, change.b} <= set(interaction.subjects)
        assert change.before != change.after or change.after in (0.0, 1.0)


def test_starving_during_a_drought_can_be_traced_to_the_drought():
    world, _ = run()
    drought = next(e for e in world.log.events if e.kind == "drought_started")
    ended = next(e for e in world.log.events if e.kind == "drought_ended")
    # Eating (phase 1) happens before the season changes (phase 2), so hunger on the tick a
    # drought starts isn't the drought's doing, and hunger on the tick it ends still is.
    starving_in_drought = [
        e for e in world.log.events if e.kind == "starving" and drought.tick < e.tick <= ended.tick
    ]
    assert starving_in_drought
    assert all(drought.id in e.caused_by for e in starving_in_drought)


def test_starving_points_only_at_the_agents_own_failed_purchases():
    world, _ = run()
    for event in world.log.events:
        if event.kind != "starving":
            continue
        for cause_id in event.caused_by:
            cause = world.log.get(cause_id)
            if cause.kind != "drought_started":
                assert cause.subjects[0] == event.subjects[0], (event, cause)


def test_gifts_are_logged_once_and_lead_back_to_a_starving_agent():
    world, _ = run()
    gifts = [e for e in world.log.events if e.kind == "gift"]
    assert gifts
    trails = [world.log.get(c).kind for g in gifts for c in g.caused_by]
    assert "starving" in trails
    per_tick_pair = [(g.tick, g.subjects) for g in gifts]
    assert len(per_tick_pair) == len(set(per_tick_pair))


def test_routine_trade_attempts_are_detail_events():
    world, _ = run()
    detail_kinds = {e.kind for e in world.log.events if e.detail}
    assert detail_kinds <= {"trade", "no_surplus", "cannot_afford", "no_offers"}
    assert "trade" in detail_kinds
