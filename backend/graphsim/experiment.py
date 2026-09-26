"""Batches of runs, defined in scenario.toml [experiments]:

    python -m graphsim.experiment ablations                # as defined in the file
    python -m graphsim.experiment ablations --seeds 1-20   # fewer seeds for a quick look
    python -m graphsim.experiment ablations --report       # just print the report again
    python -m graphsim.experiment ablations --reanalyze    # recompute measures, then report

Every (world, variant, seed) job becomes a stored run. Runs that already exist with identical
settings and code are reused, so an interrupted experiment picks up where it stopped. Jobs run in
parallel worker processes; the main process writes their results to the database.

An experiment with `branch_at` intervenes: each of those runs is branched at that tick once per
control and arm (runner.branch), and the report compares every arm with its "none" branch, seed
by seed, next to how much "reseed" (chance alone) moves the same measures.

The report (see report.py) is printed at the end and written to
runs/experiments/<name>/{runs,summary,paired}.csv.
"""

import argparse
import itertools
import json
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from graphsim import report, runner, storage
from graphsim.config import CONTROLS, Scenario, load_scenario, parse_seeds


@dataclass(frozen=True)
class Job:
    # The variant, plus any swept values, e.g. "baseline[trade.min_amount=0.2]"; prefixed with
    # the world when an experiment compares several, e.g. "hub_and_spokes/baseline"; and in an
    # experiment that intervenes, followed by the arm, e.g. "baseline:remove_top_broker".
    label: str
    scenario: str
    variant: str
    overrides: tuple[tuple[str, Any], ...]
    seed: int
    arm: str = ""  # the control or arm (intervening experiments only)
    changes: str = "[]"  # JSON: the interventions the arm applies at branch_at

    @property
    def parent(self) -> tuple:
        """What identifies the unintervened run this job branches from."""
        return (self.scenario, self.variant, self.overrides, self.seed)


def plan(scenario: Scenario, name: str, seeds: list[int] | None = None) -> list[Job]:
    """Every job of the experiment: each world, times each variant, times each swept
    combination, times each seed (and, in an experiment that intervenes, times each control
    and arm)."""
    experiment = scenario.experiments[name]
    sweep_keys = list(experiment.sweep)
    combinations = list(itertools.product(*experiment.sweep.values())) or [()]
    several_worlds = len(experiment.scenarios) > 1
    arms = {**{c: CONTROLS[c] for c in experiment.controls}, **experiment.arms}
    jobs = []
    for world in experiment.scenarios:
        for variant in experiment.variants:
            for values in combinations:
                overrides = tuple(zip(sweep_keys, values, strict=True))
                label = (f"{world}/" if several_worlds else "") + variant
                if overrides:
                    label += "[" + ", ".join(f"{k}={v}" for k, v in overrides) + "]"
                for seed in seeds or experiment.seeds:
                    if not experiment.branch_at:
                        jobs.append(Job(label, world, variant, overrides, seed))
                        continue
                    for arm, changes in arms.items():
                        changes_json = json.dumps(changes, sort_keys=True)
                        jobs.append(
                            Job(
                                f"{label}:{arm}", world, variant, overrides, seed, arm, changes_json
                            )
                        )
    return jobs


def run_experiment(
    scenario: Scenario,
    name: str,
    seeds: list[int] | None = None,
    ticks: int | None = None,
    workers: int | None = None,
) -> None:
    experiment = scenario.experiments[name]
    ticks = ticks or experiment.ticks
    conn = storage.connect(scenario.database)
    jobs = plan(scenario, name, seeds)
    storage.forget_old_labels(conn, name, sorted({job.label for job in jobs}))
    path, level = str(scenario.path), experiment.level

    # 1. The unintervened runs (in an experiment that intervenes: the parents of its branches).
    parents: dict[tuple, int] = {}
    pending: list[tuple[Any, int]] = []
    for job in {job.parent: job for job in jobs}.values() if experiment.branch_at else jobs:
        run_id, done = runner.prepare(
            conn,
            scenario,
            seed=job.seed,
            ticks=ticks,
            variant=job.variant,
            overrides=dict(job.overrides),
            level=level,
            experiment=name if not experiment.branch_at else "",
            label=job.label.split(":")[0],
            scenario_name=job.scenario,
        )
        parents[job.parent] = run_id
        if not experiment.branch_at:
            storage.assign_experiment_run(conn, name, job.label, job.seed, run_id)
        if not done:
            pending.append(((job, ticks, level), run_id))
    _compute_all(conn, name, "runs", _compute, path, pending, workers)
    if not experiment.branch_at:
        return

    # 2. The branches: every control and arm of every run, from branch_at on.
    pending = []
    for job in jobs:
        run_id, done = runner.prepare_branch(
            conn,
            scenario,
            parents[job.parent],
            experiment.branch_at,
            json.loads(job.changes),
            label=job.label,
            level=level,
            experiment=name,
        )
        storage.assign_experiment_run(conn, name, job.label, job.seed, run_id)
        if not done:
            pending.append((storage.get_run(conn, run_id), run_id))
    _compute_all(conn, name, "branches", _compute_branch, path, pending, workers)


def _compute_all(conn, name, what, compute, path, pending, workers) -> None:
    """Computes the pending runs in worker processes and stores them as they finish."""
    print(f"{name}: {what}: {len(pending)} to compute")
    if not pending:
        return
    started = time.perf_counter()
    with ProcessPoolExecutor(max_workers=workers or os.cpu_count()) as pool:
        futures = {pool.submit(compute, path, work): run_id for work, run_id in pending}
        for finished, future in enumerate(as_completed(futures), start=1):
            run_id = futures[future]
            try:
                runner.store_batches(conn, run_id, future.result())
            except Exception:
                storage.set_status(conn, run_id, "failed")
                raise
            elapsed = time.perf_counter() - started
            remaining = elapsed / finished * (len(pending) - finished)
            print(f"  {finished}/{len(pending)} done, ~{remaining:.0f}s left", end="\r")
    print(f"\n  computed {len(pending)} {what} in {time.perf_counter() - started:.0f}s")


def _compute(scenario_path: str, work: tuple[Job, int, str]) -> list[storage.Batch]:
    """Runs in a worker process: the whole simulation, returned as rows to store."""
    job, ticks, level = work
    scenario = load_scenario(scenario_path)
    cfg = scenario.config(job.variant, dict(job.overrides), scenario=job.scenario)
    return list(runner.simulate(cfg, job.seed, ticks, scenario.recording[level]))


def _compute_branch(scenario_path: str, info: dict[str, Any]) -> list[storage.Batch]:
    """Runs in a worker process: a branch (its parent's history replayed, then its own)."""
    scenario = load_scenario(scenario_path)
    cfg = scenario.config(info["variant"], info["overrides"], scenario=info["scenario"])
    recording = scenario.recording[info["level"]]
    batches = runner.simulate(
        cfg, info["seed"], info["ticks"], recording, info["interventions"], info["branch_tick"]
    )
    return list(batches)


def main() -> None:
    scenario = load_scenario()
    parser = argparse.ArgumentParser(description="Run an experiment from scenario.toml.")
    parser.add_argument("name", choices=list(scenario.experiments))
    parser.add_argument("--seeds", help="override the experiment's seeds, e.g. 1-20")
    parser.add_argument("--ticks", type=int, help="override the experiment's run length")
    parser.add_argument("--workers", type=int, help="parallel processes (default: all cores)")
    parser.add_argument("--report", action="store_true", help="only print the report")
    parser.add_argument(
        "--reanalyze",
        action="store_true",
        help="recompute the stored runs' measures (after changing analysis.py), then report",
    )
    args = parser.parse_args()

    if not (args.report or args.reanalyze):
        seeds = parse_seeds(args.seeds) if args.seeds else None
        run_experiment(scenario, args.name, seeds, args.ticks, args.workers)
    conn = storage.connect(scenario.database)
    if args.reanalyze:
        report.reanalyze(conn, [a["run_id"] for a in storage.experiment_runs(conn, args.name)])
    result = report.build(conn, scenario, args.name)
    print(report.format_text(result, scenario))
    out = Path(scenario.database).parent / "experiments" / args.name
    report.write_csvs(result, out)
    print(f"\nCSV files in {out}")


if __name__ == "__main__":
    main()
