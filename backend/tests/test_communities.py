"""Community identity over time, on hand-built partitions (no Louvain involved)."""

import networkx as nx

from graphsim.communities import track_communities
from tests.helpers import add_agent, make_world


def world_with_agents(n: int):
    world = make_world()
    agents = [add_agent(world, "farmer").id for _ in range(n)]
    return world, agents


def detect(world, tick: int, *groups: list[str]) -> dict[str, int]:
    world.tick = tick
    return track_communities(world, [set(g) for g in groups], nx.Graph())


def kinds(world) -> list[str]:
    return [e.kind for e in world.log.events if e.kind.startswith("community")]


def test_a_community_that_keeps_most_members_keeps_its_id():
    world, a = world_with_agents(6)
    first = detect(world, 1, a[0:5])
    second = detect(world, 2, a[0:4] + [a[5]])  # one member swapped
    assert first[a[0]] == second[a[0]]
    record = world.metrics.communities[second[a[0]]]
    assert record.continuations == 1
    assert abs(record.mean_turnover() - (1 - 4 / 6)) < 1e-9
    assert record.members_ever == set(a)


def test_split_creates_a_child_of_the_original():
    world, a = world_with_agents(8)
    detect(world, 1, a)
    after = detect(world, 2, a[0:4], a[4:8])
    parent_id, child_id = after[a[0]], after[a[4]]
    assert parent_id != child_id
    assert world.metrics.communities[child_id].parent == parent_id
    assert "community_split" in kinds(world)


def test_merger_ends_one_community_inside_another():
    world, a = world_with_agents(8)
    before = detect(world, 1, a[0:4], a[4:8])
    after = detect(world, 2, a)
    survivor = after[a[0]]
    absorbed = before[a[4]] if before[a[4]] != survivor else before[a[0]]
    record = world.metrics.communities[absorbed]
    assert record.fate == "merged" and record.merged_into == survivor and record.died == 2
    assert "community_merged" in kinds(world)


def test_scattered_community_dissolves():
    world, a = world_with_agents(4)
    first = detect(world, 1, a)
    detect(world, 2)
    record = world.metrics.communities[first[a[0]]]
    assert record.fate == "dissolved"
    assert record.lifespan(now=10) == 1
    assert world.metrics.alive == []


def test_break_up_into_unrelated_groups_is_a_birth_not_a_split():
    world, a = world_with_agents(12)
    first = detect(world, 1, a[0:6])
    # Two new groups that each hold only 3 of the old 6 members plus strangers.
    after = detect(world, 2, a[0:3] + a[6:9], a[3:6] + a[9:12])
    new_ids = {after[a[0]], after[a[3]]}
    old = world.metrics.communities[first[a[0]]]
    # Jaccard 3/9 >= 0.3, so one continues; the other is born fresh (not mostly from the old).
    assert first[a[0]] in new_ids
    other = (new_ids - {first[a[0]]}).pop()
    assert world.metrics.communities[other].parent is None
    assert old.fate == "alive"


def test_first_detection_is_quiet():
    world, a = world_with_agents(8)
    detect(world, 1, a[0:4], a[4:8])
    assert kinds(world) == []
