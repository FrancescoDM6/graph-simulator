from graphsim.model import Interaction, Layer
from graphsim.rules import relationships
from tests.helpers import add_agent, befriend, make_world


def test_attention_limit_drops_the_weakest_tie():
    world = make_world({"relationships.max_social_ties": 2})
    agent = add_agent(world, "farmer")
    strong, weak, medium = (add_agent(world, "miner") for _ in range(3))
    befriend(world, agent, strong, strength=0.9, trust=0.5)
    befriend(world, agent, weak, strength=0.2, trust=0.5)
    befriend(world, agent, medium, strength=0.5, trust=0.5)

    relationships.enforce_attention_limit(world)

    assert sorted(world.neighbors(agent.id, Layer.SOCIAL)) == sorted([strong.id, medium.id])
    assert world.log.events[-1].kind == "tie_dropped"


def test_faded_ties_are_pruned_with_an_event():
    world = make_world()
    a, b = add_agent(world, "farmer"), add_agent(world, "miner")
    befriend(world, a, b, strength=0.01, trust=0.5)

    relationships.prune_faded_ties(world)

    assert world.get_edge(a.id, b.id, Layer.SOCIAL) is None
    assert world.log.events[-1].kind == "tie_faded"


def test_regular_trading_partners_get_to_know_each_other():
    world = make_world()
    buyer, seller = add_agent(world, "miner"), add_agent(world, "farmer")
    sale = Interaction(buyer.id, seller.id, "food", 1.0, "success", cause="test")

    world.interactions = [sale]
    relationships.apply_interactions(world)
    assert world.get_edge(buyer.id, seller.id, Layer.SOCIAL) is None  # one trade isn't enough

    for _ in range(3):
        relationships.apply_interactions(world)
    assert world.get_edge(buyer.id, seller.id, Layer.SOCIAL) is not None


def test_crossing_the_trust_threshold_logs_an_event():
    world = make_world({"relationships.trade_friendship_at": 0.0})
    buyer, seller = add_agent(world, "miner"), add_agent(world, "farmer")
    befriend(world, buyer, seller, strength=0.5, trust=0.69)
    world.interactions = [Interaction(buyer.id, seller.id, "food", 1.0, "success", cause="x")]

    relationships.apply_interactions(world)

    assert "trusted" in [e.kind for e in world.log.events]
