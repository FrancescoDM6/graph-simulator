"""Whole-simulation checks: reproducibility, and that the default config stays 'alive'."""

import os
import subprocess
import sys
from pathlib import Path
from statistics import mean

from graphsim import engine
from graphsim.config import SimConfig
from graphsim.world_gen import build_world

BACKEND = Path(__file__).resolve().parents[1]

HISTORY_HASH_SCRIPT = """
import hashlib, json
from dataclasses import asdict
from graphsim import engine
from graphsim.config import SimConfig
from graphsim.world_gen import build_world
world = build_world(SimConfig(), seed=7)
for _ in range(300):
    engine.step(world)
events = json.dumps([asdict(e) for e in world.log.events])
metrics = json.dumps([asdict(m) for m in world.metrics.history])
print(hashlib.sha256((events + metrics).encode()).hexdigest())
"""


def run_history(seed: int, ticks: int):
    world = build_world(SimConfig(), seed)
    for _ in range(ticks):
        engine.step(world)
    return world


def test_same_seed_gives_the_same_history():
    first, second = run_history(seed=3, ticks=200), run_history(seed=3, ticks=200)
    assert first.log.events == second.log.events
    assert first.metrics.history == second.metrics.history


def test_history_does_not_depend_on_python_hash_randomization():
    # String hashing differs between Python processes, which would change the order of any
    # set iteration. Run in two processes with different hash seeds and compare.
    hashes = set()
    for hash_seed in ("1", "2"):
        env = {**os.environ, "PYTHONHASHSEED": hash_seed, "PYTHONPATH": str(BACKEND)}
        result = subprocess.run(
            [sys.executable, "-c", HISTORY_HASH_SCRIPT],
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        hashes.add(result.stdout.strip())
    assert len(hashes) == 1


def test_default_world_stays_alive_and_structured():
    world = run_history(seed=1, ticks=2000)
    history = world.metrics.history
    start_population = history[0].population
    later_half = history[len(history) // 2 :]

    assert min(m.population for m in history) >= start_population * 0.5  # no collapse
    assert 0.05 < mean(m.social_density for m in later_half) < 0.5  # neither empty nor a hairball
    assert mean(m.merchant_broker_share for m in later_half) > 0.3  # merchants are brokers
    assert max(m.communities for m in later_half) >= 2  # more than one faction
