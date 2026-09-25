"""Headless runs: python -m graphsim.cli --seed 1 --ticks 5000 [--variant no_gifting] [--set k=v]

Writes <out>/events.jsonl and <out>/metrics.csv, then prints a summary of the target
phenomena from docs/spec.md so you can tell at a glance whether a config is "interesting".
"""

import argparse
import csv
import json
import time
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from statistics import mean

from graphsim import engine
from graphsim.config import load_scenario, parse_override
from graphsim.events import Event
from graphsim.stats import TickMetrics
from graphsim.world_gen import build_world


def main() -> None:
    scenario = load_scenario()
    parser = argparse.ArgumentParser(description="Run the simulation without a UI.")
    parser.add_argument("--seed", type=int, default=scenario.seed)
    parser.add_argument("--ticks", type=int, default=scenario.ticks)
    parser.add_argument("--variant", default="baseline", choices=list(scenario.variants))
    parser.add_argument("--set", action="append", default=[], metavar="SECTION.KEY=VALUE")
    parser.add_argument("--out", type=Path, help="output folder (default: runs/seed<N>)")
    args = parser.parse_args()
    out = args.out or Path("runs") / f"seed{args.seed}"

    cfg = scenario.config(args.variant, dict(parse_override(text) for text in args.set))
    started = time.perf_counter()
    world = build_world(cfg, args.seed)
    for _ in range(args.ticks):
        engine.step(world)
        if world.tick % 500 == 0:
            print(f"  tick {world.tick}: population {len(world.agents)}")
    elapsed = time.perf_counter() - started

    write_events(world.log.events, out / "events.jsonl")
    write_metrics(world.metrics.history, out / "metrics.csv")
    print(f"\n{args.ticks} ticks in {elapsed:.1f}s -> {out}")
    print_summary(world.metrics.history, Counter(e.kind for e in world.log.events))


def write_events(events: list[Event], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for event in events:
            f.write(json.dumps(asdict(event)) + "\n")


def write_metrics(history: list[TickMetrics], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(history[0]) if history else ["tick"])
        writer.writeheader()
        writer.writerows(history)


def print_summary(history: list[TickMetrics], event_counts: Counter) -> None:
    """Reports the target phenomena from docs/spec.md."""
    if not history:
        return
    first, last = history[0], history[-1]
    later_half = history[len(history) // 2 :]

    print("\nTarget phenomena")
    print(
        f"  1. Brokers:    brokers hold {mean(m['broker_share'] for m in later_half):.0%}"
        " of trade betweenness while being "
        f"{mean(m['broker_population_share'] for m in later_half):.0%} of the population"
    )
    communities = [m["communities"] for m in later_half]
    print(
        f"  2. Factions:   communities min/avg/max = {min(communities):g}"
        f"/{mean(communities):.1f}/{max(communities):g}"
        f"; born {event_counts['community_formed']}, split {event_counts['community_split']}, "
        f"merged {event_counts['community_merged']}, dissolved "
        f"{event_counts['community_dissolved']}"
    )
    before, after = _drought_edges(history)
    if before:
        print(
            f"  3. Drought:    from the tick before each drought to its last tick: avg trust "
            f"{mean(m['avg_trust'] for m in before):.2f} -> "
            f"{mean(m['avg_trust'] for m in after):.2f}, starving "
            f"{mean(m['starving'] for m in before):.1f} -> "
            f"{mean(m['starving'] for m in after):.1f}, orgs {mean(m['orgs'] for m in before):.1f}"
            f" -> {mean(m['orgs'] for m in after):.1f}"
        )
    print(f"  4. Inequality: Gini {first['gini_coin']:.2f} -> {last['gini_coin']:.2f}")

    occupations = ", ".join(
        f"{name.split('.', 1)[1]}s {value:g}"
        for name, value in last.items()
        if name.startswith("population.")
    )
    print("\nFinal state")
    print(
        f"  population {last['population']:g} ({occupations}), orgs {last['orgs']:g}, "
        f"density {last['social_density']:.2f}, clustering {last['social_clustering']:.2f}, "
        f"components {last['social_components']:g}"
    )
    print("\nEvent counts")
    for kind, count in event_counts.most_common():
        print(f"  {kind:<20} {count}")


def _drought_edges(history: list[TickMetrics]) -> tuple[list[TickMetrics], list[TickMetrics]]:
    """Metrics from the tick before each drought starts, and from each drought's last tick."""
    before, after = [], []
    for previous, current in zip(history, history[1:], strict=False):
        if current["drought"] and not previous["drought"]:
            before.append(previous)
        if previous["drought"] and not current["drought"]:
            after.append(previous)
    return before[: len(after)], after


if __name__ == "__main__":
    main()
