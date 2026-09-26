"""Computing runs: build a world, step it, record it, store it.

    run_id = run(scenario, seed=4, ticks=2000, variant="no_gifting")   # stored in the database
    run_id = run(scenario, seed=4, ticks=2000, scenario_name="hub_and_spokes")

A run is identified by its settings (config hash), seed, length and the code version. Asking
for a run that already exists returns the stored one instead of recomputing it, and new runs
never overwrite old ones.
"""

import hashlib
import json
import subprocess
from collections.abc import Iterator
from dataclasses import asdict
from datetime import UTC, datetime
from functools import cache
from typing import Any

from graphsim import engine, storage
from graphsim.config import REPO_ROOT, RecordingSpec, Scenario, SimConfig
from graphsim.recorder import Recorder
from graphsim.world_gen import build_world

FLUSH_EVERY = 50  # ticks between database writes (and progress updates)


def simulate(
    cfg: SimConfig, seed: int, ticks: int, recording: RecordingSpec
) -> Iterator[storage.Batch]:
    """Steps a new world `ticks` times, yielding recorded rows every FLUSH_EVERY ticks."""
    world = build_world(cfg, seed)
    recorder = Recorder(world, recording)
    for _ in range(ticks):
        recorder.after_tick(engine.step(world))
        if world.tick % FLUSH_EVERY == 0 and world.tick < ticks:
            yield recorder.flush()
    yield recorder.finish()


def run(
    scenario: Scenario,
    *,
    seed: int,
    ticks: int,
    variant: str = "baseline",
    overrides: dict[str, Any] | None = None,
    level: str = "full",
    experiment: str = "",
    label: str = "",
    reuse: bool = True,
    scenario_name: str | None = None,
) -> int:
    """Computes a run (or finds an identical stored one) and returns its id. `scenario_name`
    picks the world from scenarios/ (default: scenario.toml [run] scenario)."""
    conn = storage.connect(scenario.database)
    run_id, done = prepare(
        conn,
        scenario,
        seed,
        ticks,
        variant,
        overrides,
        level,
        experiment,
        label,
        reuse,
        scenario_name=scenario_name,
    )
    if not done:
        execute(conn, scenario, run_id)
    return run_id


def prepare(
    conn,
    scenario: Scenario,
    seed: int,
    ticks: int,
    variant: str = "baseline",
    overrides: dict[str, Any] | None = None,
    level: str = "full",
    experiment: str = "",
    label: str = "",
    reuse: bool = True,
    scenario_name: str | None = None,
) -> tuple[int, bool]:
    """Creates the run's database row (or finds a finished identical run).
    Returns (run id, whether it is already done)."""
    world = scenario_name or scenario.default_scenario
    cfg = scenario.config(variant, overrides, scenario=world)
    code = code_version()
    if reuse:
        cached = storage.find_cached_run(conn, cfg.config_hash(), seed, ticks, level, code)
        if cached is not None:
            return cached, True
    run_id = storage.create_run(
        conn,
        {
            "created": datetime.now(UTC).isoformat(timespec="seconds"),
            "scenario": world,
            "variant": variant,
            "overrides": json.dumps(overrides or {}, sort_keys=True),
            "seed": seed,
            "ticks": ticks,
            "level": level,
            "config_hash": cfg.config_hash(),
            "config_json": json.dumps(asdict(cfg), sort_keys=True),
            "code_version": code,
            "experiment": experiment,
            "label": label,
            "status": "running",
            "ticks_done": 0,
        },
    )
    return run_id, False


def execute(conn, scenario: Scenario, run_id: int) -> None:
    """Computes a prepared run, writing it to the database as it goes."""
    info = storage.get_run(conn, run_id)
    assert info is not None
    cfg = _config_for(scenario, info)
    try:
        for batch in simulate(cfg, info["seed"], info["ticks"], scenario.recording[info["level"]]):
            storage.write_batch(conn, run_id, batch)
        storage.set_status(conn, run_id, "done")
    except BaseException:
        storage.set_status(conn, run_id, "failed")
        raise


def store_batches(conn, run_id: int, batches: list[storage.Batch]) -> None:
    """Writes a run computed elsewhere (e.g. in a worker process) and marks it done."""
    for batch in batches:
        storage.write_batch(conn, run_id, batch)
    storage.set_status(conn, run_id, "done")


def materialize(scenario: Scenario, run_id: int) -> int:
    """A full-detail version of a (summary-level) run, recomputed if needed. Deterministic, so
    it is the same world; refuses if scenario.toml has changed since the run was made."""
    conn = storage.connect(scenario.database)
    info = storage.get_run(conn, run_id)
    if info is None:
        raise KeyError(f"no run {run_id}")
    if info["level"] == "full":
        return run_id
    _config_for(scenario, info)  # checks the settings still match
    return run(
        scenario,
        seed=info["seed"],
        ticks=info["ticks"],
        variant=info["variant"],
        overrides=info["overrides"],
        level="full",
        experiment=info["experiment"],
        label=info["label"],
        scenario_name=info["scenario"],
    )


@cache
def code_version() -> str:
    """The git commit of the simulation code, plus a hash of any uncommitted changes to it."""
    try:
        head = _git("rev-parse", "--short", "HEAD").strip()
        changes = _git("diff", "HEAD", "--", "backend/graphsim") + _git(
            "status", "--porcelain", "--", "backend/graphsim"
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    if changes.strip():
        return f"{head}+{hashlib.sha1(changes.encode()).hexdigest()[:8]}"
    return head


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    ).stdout


def _config_for(scenario: Scenario, info: dict[str, Any]) -> SimConfig:
    cfg = scenario.config(info["variant"], info["overrides"], scenario=info["scenario"])
    if cfg.config_hash() != info["config_hash"]:
        raise ValueError(
            f"run {info['id']} was made with different settings than the scenario files now "
            f"give for {info['scenario']!r}, variant {info['variant']!r}; it can't be "
            "reproduced exactly"
        )
    return cfg
