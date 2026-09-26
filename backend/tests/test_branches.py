"""Branches: alternate histories of a stored run, replayed to their branch tick and stitched
together with their parent when read."""

import pytest

from graphsim import runner, storage
from graphsim.config import load_scenario

TICKS = 240
AT = 150  # the branch tick


@pytest.fixture
def scenario(tmp_path):
    scenario = load_scenario()
    scenario.database = tmp_path / "runs.db"
    return scenario


@pytest.fixture
def parent(scenario):
    return runner.run(scenario, seed=1, ticks=TICKS)


def test_a_branch_without_interventions_is_its_parent(scenario, parent):
    conn = storage.connect(scenario.database)
    same = runner.branch(scenario, parent, AT, [])
    assert storage.lineage(conn, same) == [(parent, 0, AT - 1), (same, AT, 1 << 62)]
    # Read through the lineage, the branch's history is its parent's, tick for tick.
    assert storage.metric_series(conn, same) == storage.metric_series(conn, parent)
    kwargs = {"include_detail": True, "limit": 100_000}
    assert storage.events(conn, same, **kwargs) == storage.events(conn, parent, **kwargs)
    assert storage.snapshots(conn, same, AT - 5, 20) == storage.snapshots(conn, parent, AT - 5, 20)
    agent = storage.agents(conn, parent)[3]["agent_id"]
    assert storage.agent_history(conn, same, agent) == storage.agent_history(conn, parent, agent)
    assert storage.flows(conn, same, agent) == storage.flows(conn, parent, agent)
    # Per-run tables come from the branch itself and cover the whole run.
    assert storage.agents(conn, same) == storage.agents(conn, parent)
    assert storage.communities(conn, same) == storage.communities(conn, parent)
    # It stores only its own ticks.
    own = conn.execute("select min(tick) from tick_metrics where run_id = ?", (same,)).fetchone()
    assert own[0] == AT


def test_removing_the_top_broker_and_following_the_trail_back(scenario, parent):
    conn = storage.connect(scenario.database)
    removed = runner.branch(
        scenario, parent, AT, [{"kind": "remove_agent", "target": "top_broker"}]
    )
    before = storage.events(conn, removed, last_tick=AT - 1, include_detail=True, limit=100_000)
    assert before == storage.events(
        conn, parent, last_tick=AT - 1, include_detail=True, limit=100_000
    )

    [intervention] = storage.events(
        conn, removed, first_tick=AT, last_tick=AT, kinds=["intervention"]
    )
    [left] = storage.events(conn, removed, first_tick=AT, last_tick=AT, kinds=["left"])
    assert left["caused_by"] == [intervention["id"]]
    # A "why?" trail from the branch reaches events stored in the parent.
    later = storage.events(conn, removed, first_tick=AT + 1, include_detail=True, limit=100_000)
    crossing = [e for e in later if any(c < intervention["id"] for c in e["caused_by"])]
    assert crossing, "expected an event after the branch point caused by one before it"
    trail = storage.causal_trail(conn, removed, crossing[0]["id"], depth=2)
    assert all(not c.get("missing") for c in trail["causes"])

    info = storage.get_run(conn, removed)
    assert info["parent_run"] == parent and info["branch_tick"] == AT
    assert info["interventions"] == [{"kind": "remove_agent", "target": "top_broker", "tick": AT}]


def test_a_branch_of_a_branch(scenario, parent):
    conn = storage.connect(scenario.database)
    first = runner.branch(scenario, parent, AT, [{"kind": "reseed"}])
    second = runner.branch(
        scenario,
        first,
        AT + 40,
        [{"kind": "give", "target": "poorest", "asset": "coin", "amount": 30}],
    )
    assert [s[0] for s in storage.lineage(conn, second)] == [parent, first, second]
    kinds = [e["kind"] for e in storage.events(conn, second, kinds=["intervention"])]
    assert kinds == ["intervention", "intervention"]  # the reseed at AT and the gift at AT + 40
    assert (
        storage.metric_series(conn, second, ["population"])["population"][: AT - 1]
        == (storage.metric_series(conn, parent, ["population"])["population"][: AT - 1])
    )
    with pytest.raises(ValueError, match="must start between"):
        runner.branch(scenario, first, AT - 10, [])  # before the branch's own start: use the parent


def test_identical_branches_are_reused(scenario, parent):
    change = [{"kind": "start_drought", "length": 30}]
    assert runner.branch(scenario, parent, AT, change) == runner.branch(
        scenario, parent, AT, change
    )
    assert runner.branch(scenario, parent, AT, change) != runner.branch(
        scenario, parent, AT + 1, change
    )


def test_branching_is_refused_when_the_parent_cant_be_replayed(scenario, parent):
    conn = storage.connect(scenario.database)
    with pytest.raises(ValueError, match="must start between"):
        runner.branch(scenario, parent, TICKS + 1, [])
    conn.execute("update runs set code_version = 'someone-else' where id = ?", (parent,))
    conn.commit()
    with pytest.raises(ValueError, match="other code"):
        runner.branch(scenario, parent, AT, [])
