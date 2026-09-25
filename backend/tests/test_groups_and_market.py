from graphsim.model import Interaction, Layer, Org
from graphsim.rules import groups, market
from tests.helpers import add_agent, befriend, make_world


def add_org(world, *members):
    org = Org(world.new_id("org"), "Test Circle", home="town-001", founded=0)
    world.add_org(org)
    for member in members:
        world.add_edge(member.id, org.id, Layer.MEMBERSHIP)
    return org


def test_agent_joins_the_org_its_trusted_friends_belong_to():
    world = make_world({"organizations.join_score": 1.2})
    a, b, newcomer = (add_agent(world, "farmer") for _ in range(3))
    befriend(world, a, b, strength=0.5, trust=0.8)
    org = add_org(world, a, b)
    befriend(world, newcomer, a, strength=0.5, trust=0.8)
    befriend(world, newcomer, b, strength=0.5, trust=0.8)

    groups.update_memberships(world)

    assert world.org_of(newcomer.id) == org.id


def test_org_with_one_member_dissolves():
    world = make_world()
    loner = add_agent(world, "farmer")
    org = add_org(world, loner)

    groups.update_memberships(world)

    assert org.id not in world.orgs
    assert world.org_of(loner.id) is None


def test_shortages_raise_prices_and_unpaid_attempts_lower_them():
    world = make_world()
    food_before, ore_before = world.prices["food"], world.prices["ore"]
    world.interactions = [
        Interaction("a", "b", "food", 0.0, "no_surplus", cause=""),
        Interaction("a", "c", "ore", 0.0, "cannot_afford", cause=""),
    ]

    market.update_prices(world)

    assert world.prices["food"] > food_before
    assert world.prices["ore"] < ore_before


def test_town_levy_moves_coin_toward_equal_without_creating_any():
    world = make_world({"prices.town_levy": 0.1})
    rich = add_agent(world, "merchant", coin=100.0)
    poor = add_agent(world, "farmer", coin=0.0)

    market.share_town_levy(world)

    assert rich.coin < 100.0
    assert poor.coin > 0.0
    assert rich.coin + poor.coin == 100.0
