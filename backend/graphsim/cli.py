"""Headless runs: python -m graphsim.cli --seed 1 --ticks 5000

Writes <out>/events.jsonl and <out>/metrics.csv, then prints a summary of the target
phenomena from docs/spec.md so you can tell at a glance whether a config is "interesting".
"""

import argparse
import csv
import json
import time
from collections import Counter
from dataclasses import asdict, fields
from pathlib import Path
from statistics import mean

from graphsim import engine
from graphsim.config import SimConfig
from graphsim.stats import TickMetrics
from graphsim.world_gen import build_world


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the simulation without a UI.")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--ticks", type=int, default=2000)
    parser.add_argument("--out", type=Path, help="output folder (default: runs/seed<N>)")
    args = parser.parse_args()
    out = args.out or Path("runs") / f"seed{args.seed}"

    started = time.perf_counter()
    world = build_world(SimConfig(), args.seed)
    for _ in range(args.ticks):
        engine.step(world)
        if world.tick % 500 == 0:
            print(f"  tick {world.tick}: population {len(world.agents)}")
    elapsed = time.perf_counter() - started

    write_events(world.log.events, out / "events.jsonl")
    write_metrics(world.metrics.history, out / "metrics.csv")
    print(f"\n{args.ticks} ticks in {elapsed:.1f}s -> {out}")
    print_summary(world.metrics.history, Counter(e.kind for e in world.log.events))


def write_events(events: list, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for event in events:
            f.write(json.dumps(asdict(event)) + "\n")


def write_metrics(history: list[TickMetrics], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[field.name for field in fields(TickMetrics)])
        writer.writeheader()
        for row in history:
            writer.writerow(asdict(row))


def print_summary(history: list[TickMetrics], event_counts: Counter) -> None:
    """Reports the four target phenomena from docs/spec.md."""
    if not history:
        return
    first, last = history[0], history[-1]
    later_half = history[len(history) // 2 :]
    drought = [m for m in history if m.drought]
    normal = [m for m in history if not m.drought]
    merchant_population_share = mean(m.merchants / max(m.population, 1) for m in later_half)

    print("\nTarget phenomena")
    print(
        f"  1. Brokers:    merchants hold {mean(m.merchant_broker_share for m in later_half):.0%}"
        f" of trade betweenness while being {merchant_population_share:.0%} of the population"
    )
    print(
        f"  2. Factions:   communities min/avg/max = {min(m.communities for m in later_half)}"
        f"/{mean(m.communities for m in later_half):.1f}/{max(m.communities for m in later_half)}"
        f"; formed {event_counts['community_formed']}x, dissolved "
        f"{event_counts['community_dissolved']}x"
    )
    if drought and normal:
        print(
            f"  3. Drought:    avg trust {mean(m.avg_trust for m in normal):.2f} normal vs "
            f"{mean(m.avg_trust for m in drought):.2f} drought; trades/tick "
            f"{mean(m.trades for m in normal):.1f} vs {mean(m.trades for m in drought):.1f}; "
            f"starving {mean(m.starving for m in normal):.1f} vs "
            f"{mean(m.starving for m in drought):.1f}"
        )
    print(f"  4. Inequality: Gini {first.gini_coin:.2f} -> {last.gini_coin:.2f}")

    print("\nFinal state")
    print(
        f"  population {last.population} (farmers {last.farmers}, miners {last.miners}, "
        f"merchants {last.merchants}), orgs {last.orgs}, density {last.social_density:.2f}, "
        f"clustering {last.social_clustering:.2f}, components {last.social_components}"
    )
    print("\nEvent counts")
    for kind, count in event_counts.most_common():
        print(f"  {kind:<20} {count}")


if __name__ == "__main__":
    main()
