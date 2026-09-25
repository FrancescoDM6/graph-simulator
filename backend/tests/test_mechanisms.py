"""Every mechanism switch in scenario.toml must actually change behaviour."""

from collections import Counter
from functools import cache

from graphsim import engine
from graphsim.config import load_scenario
from graphsim.model import Layer, World
from graphsim.world_gen import build_world

TICKS = 400  # long enough to include the first drought (tick 200)


@cache
def run(variant: str = "baseline", **overrides) -> World:
    cfg = load_scenario().config(variant, {k.replace("__", "."): v for k, v in overrides.items()})
    world = build_world(cfg, seed=1)
    for _ in range(TICKS):
        engine.step(world)
    return world


def kinds(world: World) -> Counter:
    return Counter(e.kind for e in world.log.events)


def causes(world: World, kind: str) -> Counter:
    return Counter(e.cause for e in world.log.events if e.kind == kind)


def social_edges(world: World) -> dict:
    return {k: (e.strength, e.trust) for k, e in world.edges.items() if k[2] == Layer.SOCIAL}


def test_the_baseline_has_everything_the_switches_turn_off():
    counts = kinds(run())
    for kind in ("gift", "introduced", "founded_org", "drought_started", "met"):
        assert counts[kind] > 0, kind


def test_no_gifting():
    assert kinds(run("no_gifting"))["gift"] == 0


def test_no_merchants():
    world = run("no_merchants")
    assert all(a.occupation != "merchant" for a in world.agents.values())
    assert all(m["broker_share"] == 0 for m in world.metrics.history)


def test_no_introductions():
    assert kinds(run("no_introductions"))["introduced"] == 0


def test_no_organizations():
    world = run("no_organizations")
    assert kinds(world)["founded_org"] == 0 and not world.orgs


def test_no_droughts():
    assert kinds(run("no_droughts"))["drought_started"] == 0


def test_no_meetings():
    world = run(mechanisms__meetings=False)
    assert not any(c.startswith("both live in") for c in causes(world, "met"))


def test_no_trade_friendships():
    world = run(mechanisms__trade_friendships=False)
    assert causes(world, "met")["they became regular trading partners"] == 0


def surviving_start_edges(variant: str, end: World) -> dict:
    """Tick-0 social ties between agents who are still in the world at the end (agents who
    leave take their ties with them, even when the social layer is frozen)."""
    start = build_world(load_scenario().config(variant), seed=1)
    return {k: v for k, v in social_edges(start).items() if {k[0], k[1]} <= end.agents.keys()}


def test_static_social_keeps_the_same_ties():
    end = run("static_social")
    assert social_edges(end).keys() == surviving_start_edges("static_social", end).keys()


def test_frozen_social_keeps_ties_strengths_and_trust():
    end = run("frozen_social")
    assert social_edges(end) == surviving_start_edges("frozen_social", end)


def test_random_partners_never_use_brokers():
    world = run("random_partners")
    assert kinds(world)["trade_started"] > 0
    brokered = [e for e in world.log.events if e.kind == "trade_started" and " via " in e.cause]
    assert brokered == []


def test_random_reachable_partners_differs_from_network_choice():
    assert kinds(run("random_reachable_partners")) != kinds(run())


def test_no_price_adjustment_keeps_prices_fixed():
    world = run(mechanisms__price_adjustment=False)
    assert world.prices == {"food": 1.0, "ore": 1.5}


def most_ties(world: World) -> int:
    return max(len(world.edges_of(a, Layer.SOCIAL)) for a in world.agents)


def test_attention_limit_caps_ties_and_switching_it_off_lifts_the_cap():
    limit = load_scenario().config().relationships.max_social_ties
    assert most_ties(run()) <= limit
    assert most_ties(run(mechanisms__attention_limit=False)) > limit


def test_no_town_levy_changes_the_money_distribution():
    last = run(mechanisms__town_levy=False).metrics.history[-1]
    assert last["gini_coin"] != run().metrics.history[-1]["gini_coin"]
