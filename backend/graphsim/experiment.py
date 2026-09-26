"""Batches of runs, defined in scenario.toml [experiments]:

    python -m graphsim.experiment ablations                # as defined in the file
    python -m graphsim.experiment ablations --seeds 1-20   # fewer seeds for a quick look
    python -m graphsim.experiment ablations --report       # just print the report again
    python -m graphsim.experiment ablations --reanalyze    # recompute measures, then report

Every (variant, seed) job becomes a stored run. Runs that already exist with identical settings
and code are reused, so an interrupted experiment picks up where it stopped. Jobs run in
parallel worker processes; the main process writes their results to the database.

The report (see report.py) is printed at the end and written to
runs/experiments/<name>/{runs,summary,paired}.csv.
"""

import argparse
import itertools
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from graphsim import report, runner, storage
from graphsim.config import Scenario, load_scenario, parse_seeds


@dataclass(frozen=True)
class Job:
    # The variant, plus any swept values, e.g. "baseline[trade.min_amount=0.2]"; prefixed with
    # the world when an experiment compares several, e.g. "hub_and_spokes/baseline".
    label: str
    scenario: str
    variant: str
    overrides: tuple[tuple[str, Any], ...]
    seed: int


def plan(scenario: Scenario, name: str, seeds: list[int] | None = None) -> list[Job]:
    """Every job of the experiment: each world, times each variant, times each swept
    combination, times each seed."""
    experiment = scenario.experiments[name]
    sweep_keys = list(experiment.sweep)
    combinations = list(itertools.product(*experiment.sweep.values())) or [()]
    several_worlds = len(experiment.scenarios) > 1
    jobs = []
    for world in experiment.scenarios:
        for variant in experiment.variants:
            for values in combinations:
                overrides = tuple(zip(sweep_keys, values, strict=True))
                label = (f"{world}/" if several_worlds else "") + variant
                if overrides:
                    label += "[" + ", ".join(f"{k}={v}" for k, v in overrides) + "]"
                for seed in seeds or experiment.seeds:
                    jobs.append(Job(label, world, variant, overrides, seed))
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

    pending: list[tuple[Job, int]] = []
    for job in jobs:
        run_id, done = runner.prepare(
            conn,
            scenario,
            seed=job.seed,
            ticks=ticks,
            variant=job.variant,
            overrides=dict(job.overrides),
            level=experiment.level,
            experiment=name,
            label=job.label,
            scenario_name=job.scenario,
        )
        storage.assign_experiment_run(conn, name, job.label, job.seed, run_id)
        if not done:
            pending.append((job, run_id))
    print(f"{name}: {len(jobs)} runs, {len(jobs) - len(pending)} already stored")
    if not pending:
        return

    started = time.perf_counter()
    with ProcessPoolExecutor(max_workers=workers or os.cpu_count()) as pool:
        futures = {
            pool.submit(_compute, str(scenario.path), job, ticks, experiment.level): run_id
            for job, run_id in pending
        }
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
    print(f"\n  computed {len(pending)} runs in {time.perf_counter() - started:.0f}s")


def _compute(scenario_path: str, job: Job, ticks: int, level: str) -> list[storage.Batch]:
    """Runs in a worker process: the whole simulation, returned as rows to store."""
    scenario = load_scenario(scenario_path)
    cfg = scenario.config(job.variant, dict(job.overrides), scenario=job.scenario)
    return list(runner.simulate(cfg, job.seed, ticks, scenario.recording[level]))


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
