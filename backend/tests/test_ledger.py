"""The resource ledger is complete: every change to an agent's coin or goods is recorded."""

from collections import defaultdict

import pytest

from graphsim import engine
from graphsim.config import load_scenario
from graphsim.model import FLOW_CATEGORIES, World
from graphsim.world_gen import build_world

TICKS = 400  # includes a drought, gifts, departures and arrivals


def holdings(world: World) -> dict[tuple[str, str], float]:
    """(agent, asset) -> amount held, for every agent now in the world."""
    held = {}
    for agent in world.agents.values():
        held[(agent.id, "coin")] = agent.coin
        for good, amount in agent.inventory.items():
            held[(agent.id, good)] = amount
    return held


@pytest.mark.parametrize("variant", ["baseline", "no_gifting", "random_partners", "no_merchants"])
def test_flows_add_up_to_every_change_in_holdings(variant):
    world = build_world(load_scenario().config(variant), seed=3)
    # The endowments recorded while the world was built account for everything at tick 0.
    endowed = defaultdict(float)
    for flow in world.flows:
        endowed[(flow.agent, flow.asset)] += flow.amount
    assert endowed == pytest.approx(holdings(world))

    before = holdings(world)
    for _ in range(TICKS):
        engine.step(world)
        after = holdings(world)
        recorded = defaultdict(float)
        for flow in world.flows:
            assert flow.category in FLOW_CATEGORIES
            recorded[(flow.agent, flow.asset)] += flow.amount
        for key in before.keys() | after.keys() | recorded.keys():
            change = after.get(key, 0.0) - before.get(key, 0.0)  # leaving/arriving = 0 held
            assert recorded.get(key, 0.0) == pytest.approx(change, abs=1e-9), (world.tick, key)
        before = after


def test_commissions_name_the_pair_and_the_trade():
    world = build_world(load_scenario().config(), seed=1)
    commissions = []
    for _ in range(100):
        engine.step(world)
        commissions += [f for f in world.flows if f.category == "commission"]
    assert commissions
    for flow in commissions:
        trade = world.log.get(flow.event_id)
        buyer, seller = flow.counterparty.split(">")
        assert trade.kind == "trade" and trade.subjects[:2] == (buyer, seller)
        assert flow.agent in trade.subjects  # the broker is the trade's third subject
