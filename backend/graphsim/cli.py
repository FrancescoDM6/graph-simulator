"""One run from the command line:

    python -m graphsim.cli --seed 4 --ticks 2000 [--variant no_gifting] [--set trade.min_amount=0.2]

The run is stored in the run database (scenario.toml [run] database) like any other, so it can
be opened in the viewer or analysed later; an identical earlier run is reused, not recomputed.
Prints the run's measures and which phenomena it shows. For many seeds, use graphsim.experiment.
"""

import argparse
import time

from graphsim import runner, storage
from graphsim.config import load_scenario, parse_override


def main() -> None:
    scenario = load_scenario()
    parser = argparse.ArgumentParser(description="Compute one run and summarize it.")
    parser.add_argument("--seed", type=int, default=scenario.seed)
    parser.add_argument("--ticks", type=int, default=scenario.ticks)
    parser.add_argument("--variant", default="baseline", choices=list(scenario.variants))
    parser.add_argument("--set", action="append", default=[], metavar="SECTION.KEY=VALUE")
    parser.add_argument("--level", default="full", choices=list(scenario.recording))
    parser.add_argument("--label", default="")
    parser.add_argument("--rerun", action="store_true", help="recompute even if stored")
    args = parser.parse_args()

    started = time.perf_counter()
    run_id = runner.run(
        scenario,
        seed=args.seed,
        ticks=args.ticks,
        variant=args.variant,
        overrides=dict(parse_override(text) for text in args.set),
        level=args.level,
        label=args.label,
        reuse=not args.rerun,
    )
    elapsed = time.perf_counter() - started

    conn = storage.connect(scenario.database)
    measures = storage.measures(conn, run_id)
    print(f"run {run_id}: seed {args.seed}, {args.variant}, {args.ticks} ticks ({elapsed:.1f}s)")
    print(f"stored in {scenario.database}\n")
    print("Phenomena")
    for name, phenomenon in scenario.phenomena.items():
        value = measures.get(phenomenon.measure, float("nan"))
        verdict = "present" if phenomenon.is_present(value) else "absent"
        print(f"  {name:<20} {verdict:<8} {phenomenon.measure} = {value:.3f}")
    print("\nMeasures")
    for name, value in measures.items():
        print(f"  {name:<28} {value:.4f}")
    print("\nEvent counts (detail events only in full-level runs)")
    counts = storage.event_counts(conn, run_id)
    for kind, count in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {kind:<20} {count}")


if __name__ == "__main__":
    main()
