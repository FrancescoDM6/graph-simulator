"""Milestones are explained by the agent's own recorded ledger entries."""

from functools import cache

from graphsim import engine
from graphsim.config import load_scenario
from graphsim.model import World
from graphsim.world_gen import build_world


@cache
def run() -> World:
    world = build_world(load_scenario().config(), seed=1)
    for _ in range(400):
        engine.step(world)
    return world


def milestones(world: World, *kinds: str):
    return [e for e in world.log.events if e.kind in kinds]


def test_nobody_is_wealthy_or_poor_while_everyone_holds_the_same():
    early = [e for e in milestones(run(), "became_wealthy", "became_poor") if e.tick < 20]
    assert early == []


def test_wealth_milestones_point_at_the_agents_own_trades():
    world = run()
    found = milestones(world, "became_wealthy", "became_poor")
    assert found
    for event in found:
        assert event.cause.startswith("last 100 ticks: earned")
        for cause_id in event.caused_by:
            cause = world.log.get(cause_id)
            assert cause.kind in ("trade", "gift")
            assert event.subjects[0] in cause.subjects


def test_a_broker_becomes_wealthy_through_commissions():
    world = run()
    brokers = {a.id for a in world.agents.values() if a.occupation == "merchant"}
    wealthy_brokers = [e for e in milestones(world, "became_wealthy") if e.subjects[0] in brokers]
    assert wealthy_brokers
    assert "commission" in wealthy_brokers[0].cause
