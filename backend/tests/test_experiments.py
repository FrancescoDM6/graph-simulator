"""Experiments: job planning, parallel runs that match in-process runs, and report statistics."""

import pytest

from graphsim import analysis, experiment, report, runner, storage
from graphsim.config import ExperimentSpec, load_scenario


@pytest.fixture
def scenario(tmp_path):
    scenario = load_scenario()
    scenario.database = tmp_path / "runs.db"
    return scenario


def test_plan_expands_variants_sweeps_and_seeds(scenario):
    jobs = experiment.plan(scenario, "commission_sweep", seeds=[1, 2])
    labels = {job.label for job in jobs}
    assert len(jobs) == 4 * 2  # four commission values, two seeds
    assert "baseline[trade.broker_commission=0.1]" in labels
    assert {job.overrides for job in jobs} == {
        (("trade.broker_commission", v),) for v in (0.1, 0.3, 0.5, 0.8)
    }


def test_worker_runs_match_in_process_runs_and_feed_the_report(scenario):
    scenario.raw["experiments"]["ablations"]["variants"] = ["baseline", "no_gifting"]
    scenario.experiments["ablations"] = type(scenario.experiments["ablations"])(
        **{**scenario.experiments["ablations"].__dict__, "variants": ["baseline", "no_gifting"]}
    )
    experiment.run_experiment(scenario, "ablations", seeds=[1, 2], ticks=60, workers=2)
    conn = storage.connect(scenario.database)
    assignments = storage.experiment_runs(conn, "ablations")
    assert len(assignments) == 4

    # The same job computed in this process gives identical stored results.
    worker_run = next(a for a in assignments if a["label"] == "no_gifting" and a["seed"] == 2)
    local_run = runner.run(
        scenario, seed=2, ticks=60, variant="no_gifting", level="summary", reuse=False
    )
    assert storage.metric_series(conn, worker_run["run_id"]) == storage.metric_series(
        conn, local_run
    )
    assert storage.measures(conn, worker_run["run_id"]) == storage.measures(conn, local_run)

    result = report.build(conn, scenario, "ablations")
    assert result["labels"] == ["baseline", "no_gifting"]
    paired = {(p["label"], p["measure"]): p for p in result["paired"]}
    assert paired[("no_gifting", "gifts_per_1000")]["n"] == 2
    assert "drought_shock" in report.format_text(result, scenario)

    # Running again reuses stored runs (any identical run will do) and computes nothing new.
    runs_before = len(storage.list_runs(conn))
    experiment.run_experiment(scenario, "ablations", seeds=[1, 2], ticks=60, workers=2)
    assert len(storage.list_runs(conn)) == runs_before
    again = storage.experiment_runs(conn, "ablations")
    assert [(a["label"], a["seed"]) for a in again] == [
        (a["label"], a["seed"]) for a in assignments
    ]


def test_wilson_interval_behaves_at_the_edges():
    low, high = report.wilson_interval(0, 10)
    assert low == 0.0 and 0.25 < high < 0.35
    low, high = report.wilson_interval(10, 10)
    assert 0.65 < low < 0.75 and high == 1.0
    low, high = report.wilson_interval(95, 100)
    assert low < 0.95 < high


def test_percentile_interpolates():
    assert report.percentile([1, 2, 3, 4, 5], 50) == 3
    assert report.percentile([0, 10], 5) == pytest.approx(0.5)


def test_measures_on_a_synthetic_run():
    drought = [(t, 1.0 if 10 <= t < 20 else 0.0) for t in range(30)]
    run = analysis.RunData(
        series={
            "drought": drought,
            "starving": [(t, 5.0 if 10 <= t < 20 else 0.0) for t in range(30)],
            "gifts": [(t, 0.0) for t in range(30)],
            "avg_trust": [(t, 0.5 if t < 10 else 0.7) for t in range(30)],
            "broker_share": [(t, 0.6) for t in range(30)],
            "broker_population_share": [(t, 0.1) for t in range(30)],
            "gini_coin": [(t, t / 100) for t in range(30)],
            "population": [(t, 30.0 - (t == 15) * 6) for t in range(30)],
        },
        communities=[
            {"born": 1, "died": None, "mean_turnover": 0.0, "continuations": 29},  # founding
            {"born": 5, "died": 7, "mean_turnover": 0.5, "continuations": 2},  # flicker
            {"born": 5, "died": None, "mean_turnover": 0.1, "continuations": 20},
        ],
        event_counts={"community_split": 3},
        ticks=30,
        min_lifespan=5,
    )
    measures = analysis.compute_measures(run)
    assert measures["broker_share_ratio"] == pytest.approx(6.0)
    assert measures["drought_starvation_ratio"] == pytest.approx(5.1 / 0.1)
    assert measures["drought_trust_change"] == pytest.approx(0.2)
    assert measures["gini_rise"] == pytest.approx(0.29)
    assert measures["min_population_ratio"] == pytest.approx(0.8)
    assert measures["community_flicker_share"] == pytest.approx(0.5)
    assert measures["community_median_lifespan"] == 25
    assert measures["splits_per_1000"] == pytest.approx(100)


def two_worlds(scenario, sweep=None) -> str:
    """Adds an experiment comparing two worlds (and returns its name)."""
    scenario.experiments["worlds"] = ExperimentSpec(
        description="test",
        seeds=[1, 2],
        ticks=40,
        level="summary",
        scenarios=["three_towns", "hub_and_spokes"],
        variants=["baseline", "no_gifting"],
        sweep=sweep or {},
    )
    return "worlds"


def test_plan_crosses_worlds_with_variants_and_prefixes_labels(scenario):
    jobs = experiment.plan(scenario, two_worlds(scenario))
    assert len(jobs) == 2 * 2 * 2
    assert {(job.label, job.scenario) for job in jobs} == {
        ("three_towns/baseline", "three_towns"),
        ("three_towns/no_gifting", "three_towns"),
        ("hub_and_spokes/baseline", "hub_and_spokes"),
        ("hub_and_spokes/no_gifting", "hub_and_spokes"),
    }
    # One world: labels stay as they always were.
    assert {job.label for job in experiment.plan(scenario, "ablations", seeds=[1])} >= {"baseline"}


def test_variants_are_paired_with_their_own_worlds_baseline(scenario):
    name = two_worlds(scenario)
    experiment.run_experiment(scenario, name, workers=2)
    conn = storage.connect(scenario.database)
    result = report.build(conn, scenario, name)
    pairs = {(p["label"], p["baseline"]) for p in result["paired"]}
    assert pairs == {
        ("three_towns/no_gifting", "three_towns/baseline"),
        ("hub_and_spokes/no_gifting", "hub_and_spokes/baseline"),
    }  # no baseline is ever paired with another world's
    runs = {r["label"]: r["run_id"] for r in result["runs"]}
    assert storage.get_run(conn, runs["hub_and_spokes/baseline"])["scenario"] == "hub_and_spokes"
    assert "hub_and_spokes/no_gifting" in report.format_text(result, scenario)


def test_generator_parameters_can_be_swept(scenario):
    scenario.experiments["bridges"] = ExperimentSpec(
        description="test",
        seeds=[1],
        ticks=10,
        level="summary",
        scenarios=["two_regions"],
        variants=["baseline"],
        sweep={"generator.bridges": [1, 3]},
    )
    experiment.run_experiment(scenario, "bridges", workers=1)
    conn = storage.connect(scenario.database)
    labels = {a["label"]: a["run_id"] for a in storage.experiment_runs(conn, "bridges")}
    assert set(labels) == {"baseline[generator.bridges=1]", "baseline[generator.bridges=3]"}
    one, three = (storage.get_run(conn, labels[f"baseline[generator.bridges={b}]"]) for b in (1, 3))
    assert one["config_hash"] != three["config_hash"]  # different maps
    # ... so they are different worlds, and never paired with each other.
    assert report.build(conn, scenario, "bridges")["paired"] == []

    # After the sweep changes, the report shows only the labels the experiment now has.
    scenario.experiments["bridges"] = type(scenario.experiments["bridges"])(
        **{**scenario.experiments["bridges"].__dict__, "sweep": {"generator.bridges": [3]}}
    )
    experiment.run_experiment(scenario, "bridges", workers=1)
    assert report.build(conn, scenario, "bridges")["labels"] == ["baseline[generator.bridges=3]"]
