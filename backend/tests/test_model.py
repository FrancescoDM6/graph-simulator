from graphsim.model import Layer, Occupation
from tests.helpers import add_agent, make_world


def test_edges_are_undirected():
    world = make_world()
    a, b = add_agent(world, Occupation.FARMER), add_agent(world, Occupation.MINER)
    world.add_edge(b.id, a.id, Layer.SOCIAL, strength=0.7)

    assert world.get_edge(a.id, b.id, Layer.SOCIAL).strength == 0.7
    assert world.neighbors(a.id, Layer.SOCIAL) == [b.id]


def test_layers_are_separate_edges_between_the_same_pair():
    world = make_world()
    a, b = add_agent(world, Occupation.FARMER), add_agent(world, Occupation.MINER)
    world.add_edge(a.id, b.id, Layer.SOCIAL)
    world.add_edge(a.id, b.id, Layer.TRADE)

    assert world.neighbors(a.id, Layer.SOCIAL) == [b.id]
    assert world.neighbors(a.id, Layer.TRADE) == [b.id]
    world.remove_edge(world.get_edge(a.id, b.id, Layer.TRADE).key)
    assert world.get_edge(a.id, b.id, Layer.SOCIAL) is not None


def test_removing_a_node_removes_its_edges():
    world = make_world()
    a, b = add_agent(world, Occupation.FARMER), add_agent(world, Occupation.MINER)
    world.add_edge(a.id, b.id, Layer.SOCIAL)

    world.remove_node(a.id)

    assert a.id not in world.agents
    assert world.neighbors(b.id, Layer.SOCIAL) == []
    assert all(a.id not in key for key in world.edges)
