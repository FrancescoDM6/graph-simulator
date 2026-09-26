"""Interventions: each kind does what it says, leaves a trail, and keeps the ledger complete."""

from collections import defaultdict

import pytest

from graphsim import engine, interventions
from graphsim.config import load_scenario
from graphsim.interventions import InterventionError
from graphsim.model import FLOW_CATEGORIES, Layer, World
from graphsim.world_gen import build_world


def world_with(*specs, seed: int = 2) -> World:
    world = build_world(load_scenario().config(), seed=seed)
    interventions.schedule(world, list(specs))
    return world


def run_to(world: World, tick: int) -> None:
    while world.tick < tick:
        engine.step(world)


def logged(world: World, kind: str = "intervention"):
    return [e for e in world.log.events if e.kind == kind]


def town(world: World, name: str) -> str:
    return next(t.id for t in world.towns.values() if t.name == name)


def test_bad_interventions_are_clear_errors():
    with pytest.raises(InterventionError, match="unknown intervention kind"):
        interventions.validate({"tick": 5, "kind": "teleport"})
    with pytest.raises(InterventionError, match="takes"):
        interventions.validate({"tick": 5, "kind": "give", "target": "richest"})
    with pytest.raises(InterventionError, match="wrong type"):
        interventions.validate({"tick": 5, "kind": "start_drought", "length": "long"})
    with pytest.raises(InterventionError, match="tick"):
        interventions.validate({"tick": 0, "kind": "reseed"})


def test_removing_the_top_broker_leaves_a_trail():
    world = world_with({"tick": 150, "kind": "remove_agent", "target": "top_broker"})
    run_to(world, 149)
    broker = world.metrics.top_broker
    assert broker in world.agents
    run_to(world, 150)
    assert broker not in world.agents
    [removal] = logged(world)
    left = next(e for e in world.log.events if e.kind == "left" and e.subjects[0] == broker)
    assert left.caused_by == (removal.id,) and left.tick == 150


def test_skipped_interventions_are_logged():
    world = world_with(
        {"tick": 3, "kind": "add_site", "town": "town:Atlantis", "site_kind": "farm", "scale": 1.0}
    )
    run_to(world, 3)
    [event] = logged(world)
    assert "skipped" in event.message


def test_give_subsidize_and_remove_keep_the_ledger_complete():
    world = world_with(
        {"tick": 20, "kind": "give", "target": "richest", "asset": "coin", "amount": 50},
        {"tick": 30, "kind": "give", "target": "occupation:farmer", "asset": "food", "amount": 5},
        {"tick": 40, "kind": "subsidize", "occupation": "miner", "coin": 1.5, "ticks": 10},
        {"tick": 60, "kind": "remove_agent", "target": "poorest"},
        {"tick": 70, "kind": "give", "target": "richest", "asset": "coin", "amount": -1e9},
    )

    def holdings():
        return {
            (a.id, asset): amount
            for a in world.agents.values()
            for asset, amount in [("coin", a.coin), *a.inventory.items()]
        }

    before = holdings()
    categories = set()
    for _ in range(80):
        engine.step(world)
        after = holdings()
        recorded = defaultdict(float)
        for flow in world.flows:
            assert flow.category in FLOW_CATEGORIES
            categories.add(flow.category)
            recorded[(flow.agent, flow.asset)] += flow.amount
        for key in before.keys() | after.keys() | recorded.keys():
            change = after.get(key, 0.0) - before.get(key, 0.0)
            assert recorded.get(key, 0.0) == pytest.approx(change, abs=1e-9), (world.tick, key)
        before = after
    assert {"intervention", "subsidy", "departure"} <= categories
    assert min(a.coin for a in world.agents.values()) >= 0  # taking never goes below zero


def test_droughts_can_be_started_and_ended():
    world = world_with(
        {"tick": 50, "kind": "start_drought", "length": 20},
        {"tick": 210, "kind": "end_drought"},  # the natural drought runs from 200
    )
    run_to(world, 49)
    assert not world.drought
    run_to(world, 50)
    assert world.drought
    started = [e for e in world.log.events if e.kind == "drought_started"][-1]
    assert started.caused_by == (logged(world)[0].id,)
    run_to(world, 69)
    assert world.drought
    run_to(world, 70)
    assert not world.drought
    run_to(world, 209)
    assert world.drought  # the dry season, as usual
    run_to(world, 211)
    assert not world.drought
    run_to(world, 259)
    assert not world.drought  # stays off for the rest of that season


def test_a_new_road_lets_merchants_reach_across_it():
    world = world_with(
        {"tick": 5, "kind": "add_road", "between": ["town:Ashford", "town:Stonehold"]}
    )
    ashford, stonehold = town(world, "Ashford"), town(world, "Stonehold")
    run_to(world, 5)
    assert world.get_edge(ashford, stonehold, Layer.ACCESS) is not None
    merchants = [
        a for a in world.agents_in_town(ashford) if world.agents[a].occupation == "merchant"
    ]
    assert merchants and all(stonehold in world.towns_reachable_by(m) for m in merchants)
    interventions.schedule(
        world, [{"tick": 6, "kind": "remove_road", "between": ["town:Ashford", "town:Stonehold"]}]
    )
    run_to(world, 6)
    assert world.get_edge(ashford, stonehold, Layer.ACCESS) is None
    assert all(stonehold not in world.towns_reachable_by(m) for m in merchants)


def test_sites_can_be_opened_and_closed():
    world = world_with(
        {
            "tick": 5,
            "kind": "add_site",
            "town": "town:Stonehold",
            "site_kind": "farm",
            "scale": 0.5,
        },
        {"tick": 6, "kind": "remove_site", "target": "site:Iron Mine"},
    )
    run_to(world, 6)
    names = {s.name: s for s in world.sites.values()}
    assert "Iron Mine" not in names
    new_farm = names["New Farm (Stonehold)"]
    assert new_farm.capacity == pytest.approx(world.cfg.site_kinds["farm"].capacity / 2)


def test_ties_trust_and_organizations():
    link = {"between": ["richest", "poorest"], "layer": "social", "strength": 0.9, "trust": 0.8}
    world = world_with({"tick": 5, "kind": "link", **link})
    run_to(world, 5)
    rich, poor = logged(world)[0].subjects  # who "richest" and "poorest" were at tick 5
    assert world.get_edge(rich, poor, Layer.SOCIAL).trust == pytest.approx(0.8)

    interventions.schedule(world, [
        {"tick": 6, "kind": "found_org", "members": [rich, poor]},
        {"tick": 7, "kind": "set_trust", "between": [rich, poor], "value": 0.1},
        {"tick": 8, "kind": "sever", "between": [rich, poor], "layer": "social"},
    ])  # fmt: skip
    run_to(world, 6)
    assert world.org_of(rich) == world.org_of(poor) is not None
    run_to(world, 7)  # (distrust then makes them leave the org: the rules still apply)
    assert any(c.after == pytest.approx(0.1) for c in world.trust_changes)  # in the trust ledger
    run_to(world, 8)
    assert world.get_edge(rich, poor, Layer.SOCIAL) is None


def test_settings_can_change_mid_run():
    world = world_with(
        {"tick": 5, "kind": "set", "setting": "trade.broker_commission", "value": 0.9}
    )
    run_to(world, 5)
    assert world.cfg.trade.broker_commission == 0.9
    bad = world_with({"tick": 2, "kind": "set", "setting": "trade.no_such_thing", "value": 1})
    with pytest.raises(InterventionError, match="not a key"):
        run_to(bad, 2)


def test_reseeding_changes_chance_only_and_is_repeatable():
    plain, same = world_with(), world_with()
    reseeded = world_with({"tick": 100, "kind": "reseed"})
    again = world_with({"tick": 100, "kind": "reseed"})
    for world in (plain, same, reseeded, again):
        run_to(world, 250)
    assert plain.metrics.history == same.metrics.history  # nothing scheduled: nothing changes
    assert reseeded.metrics.history[:99] == plain.metrics.history[:99]  # identical before
    assert reseeded.metrics.history != plain.metrics.history  # different afterwards
    assert reseeded.metrics.history == again.metrics.history  # but the same every time
