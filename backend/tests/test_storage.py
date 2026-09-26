"""Stored runs: recording is faithful, runs are reused not recomputed, nothing is overwritten."""

import pytest

from graphsim import engine, runner, serialize, storage
from graphsim.config import load_scenario
from graphsim.world_gen import build_world

TICKS = 120


@pytest.fixture
def scenario(tmp_path):
    scenario = load_scenario()
    scenario.database = tmp_path / "runs.db"
    return scenario


def plain_world(seed: int, ticks: int, variant: str = "baseline"):
    world = build_world(load_scenario().config(variant), seed)
    for _ in range(ticks):
        engine.step(world)
    return world


def test_stored_run_matches_an_unrecorded_simulation(scenario):
    run_id = runner.run(scenario, seed=2, ticks=TICKS)
    conn = storage.connect(scenario.database)
    stored = storage.metric_series(conn, run_id, ["gini_coin", "population"])
    world = plain_world(seed=2, ticks=TICKS)
    assert [v for _, v in stored["gini_coin"]] == [m["gini_coin"] for m in world.metrics.history]
    assert [v for _, v in stored["population"]] == [m["population"] for m in world.metrics.history]


def test_snapshot_at_a_tick_is_the_world_at_that_tick(scenario):
    run_id = runner.run(scenario, seed=2, ticks=TICKS)
    conn = storage.connect(scenario.database)
    (stored,) = storage.snapshots(conn, run_id, first=60, count=1)
    expected = serialize.snapshot(plain_world(seed=2, ticks=60), [])
    del expected["events"]
    assert stored == expected


def test_identical_runs_are_reused_and_different_ones_are_new(scenario):
    first = runner.run(scenario, seed=3, ticks=50)
    assert runner.run(scenario, seed=3, ticks=50) == first
    assert runner.run(scenario, seed=3, ticks=50, variant="no_gifting") != first
    rerun = runner.run(scenario, seed=3, ticks=50, reuse=False)
    assert rerun != first
    conn = storage.connect(scenario.database)
    assert {r["id"] for r in storage.list_runs(conn)} >= {first, rerun}  # nothing overwritten


def test_summary_runs_are_small_and_can_be_materialized(scenario):
    summary_id = runner.run(scenario, seed=4, ticks=TICKS, level="summary")
    conn = storage.connect(scenario.database)
    assert storage.snapshots(conn, summary_id, 0, 5) == []
    assert all(not e["detail"] for e in storage.events(conn, summary_id, include_detail=True))

    full_id = runner.materialize(scenario, summary_id)
    assert full_id != summary_id
    assert len(storage.snapshots(conn, full_id, 0, 5)) == 5
    # Same world: the summary's (sampled) metrics agree with the full run's at those ticks.
    summary = dict(storage.metric_series(conn, summary_id, ["gini_coin"])["gini_coin"])
    full = dict(storage.metric_series(conn, full_id, ["gini_coin"])["gini_coin"])
    assert all(full[tick] == value for tick, value in summary.items())
    assert storage.measures(conn, summary_id).keys() == storage.measures(conn, full_id).keys()


def test_causal_trail_and_agent_history_come_back_from_the_database(scenario):
    run_id = runner.run(scenario, seed=1, ticks=TICKS)
    conn = storage.connect(scenario.database)
    trusted = storage.events(conn, run_id, kinds=["trusted"], limit=1)
    assert trusted
    trail = storage.causal_trail(conn, run_id, trusted[0]["id"])
    (interaction,) = trail["causes"]
    assert interaction["kind"] in ("trade", "gift")
    assert set(trusted[0]["subjects"]) <= set(interaction["subjects"])

    agent = storage.agents(conn, run_id)[0]
    history = storage.agent_history(conn, run_id, agent["agent_id"])
    assert len(history) == (agent["departed"] or TICKS + 1) - max(agent["arrived"], 1)
    ledger = storage.trust_changes(conn, run_id, agent["agent_id"])
    assert all(agent["agent_id"] in (c["a"], c["b"]) for c in ledger)


def test_changed_scenario_refuses_to_materialize_an_old_run(scenario):
    summary_id = runner.run(scenario, seed=5, ticks=30, level="summary")
    scenario.raw["trade"]["gift_amount"] = 3.0  # scenario.toml "edited" since the run
    with pytest.raises(ValueError, match="different settings"):
        runner.materialize(scenario, summary_id)


def test_stored_flows_add_up_to_the_lifetime_totals(scenario):
    run_id = runner.run(scenario, seed=1, ticks=TICKS)
    conn = storage.connect(scenario.database)
    agent = storage.agents(conn, run_id)[0]["agent_id"]
    summed: dict[tuple[str, str], float] = {}
    for flow in storage.flows(conn, run_id, agent):
        key = (flow["asset"], flow["category"])
        summed[key] = summed.get(key, 0.0) + flow["amount"]
    totals = {
        (t["asset"], t["category"]): t["amount"] for t in storage.agent_totals(conn, run_id, agent)
    }
    assert summed.keys() == totals.keys()
    assert all(abs(summed[k] - totals[k]) < 1e-3 for k in totals)


def test_community_and_org_histories_include_internal_stats(scenario):
    run_id = runner.run(scenario, seed=1, ticks=400)
    conn = storage.connect(scenario.database)
    community = storage.communities(conn, run_id)[0]["community_id"]
    history = storage.community_history(conn, run_id, community)
    assert history and all(0 <= row["density"] <= 1 for row in history)
    assert any(row["trust"] is not None for row in history)
    org_ids = conn.execute(
        "select distinct org_id from org_ticks where run_id = ?", (run_id,)
    ).fetchall()
    assert org_ids, "seed 1 founds an organization within 400 ticks"
    org_rows = storage.org_history(conn, run_id, org_ids[0]["org_id"])
    assert all(row["size"] == len(row["members"]) for row in org_rows)


def test_runs_from_before_scenarios_are_named_three_towns(scenario):
    conn = storage.connect(scenario.database)
    run_id = runner.run(scenario, seed=1, ticks=5, level="summary")
    assert storage.get_run(conn, run_id)["scenario"] == "three_towns"
    conn.execute("update runs set scenario = 'scenario' where id = ?", (run_id,))
    storage._name_old_worlds(conn)
    assert storage.get_run(conn, run_id)["scenario"] == "three_towns"
