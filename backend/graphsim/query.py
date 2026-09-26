"""Look at stored runs from the command line (no extra packages needed):

    uv run --project backend python -m graphsim.query runs                  # every run, newest last
    uv run --project backend python -m graphsim.query show 1740             # one run's summary
    uv run --project backend python -m graphsim.query metrics 1740 gini_coin starving --every 100
    uv run --project backend python -m graphsim.query events 1740 --kind starving --limit 20
    uv run --project backend python -m graphsim.query agent 1740 agent-004  # one agent's life
    uv run --project backend python -m graphsim.query sql "select ... from ... where run_id = 1740"

(From backend/, `uv run python -m graphsim.query ...` does the same.) Add `--csv out.csv` to
save a table instead of printing it. The readers are storage.py's, so a branch shows its
parent's history before its branch tick, as in the viewer. The tables are described at the top
of storage.py.
"""

import argparse
import csv
import sys
from collections.abc import Sequence
from typing import Any

from graphsim import storage
from graphsim.config import load_scenario

MAX_WIDTH = 60  # longer cells are cut short when printed (never in CSV files)


def show_table(rows: Sequence[dict[str, Any]], csv_path: str | None = None) -> None:
    """Rows as an aligned text table, or into a CSV file."""
    if csv_path:
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else [])
            writer.writeheader()
            writer.writerows(rows)
        print(f"{len(rows)} rows written to {csv_path}")
        return
    if not rows:
        print("(no rows)")
        return
    columns = list(rows[0])
    text = [[_cell(row.get(c)) for c in columns] for row in rows]
    widths = [max(len(c), *(len(r[i]) for r in text)) for i, c in enumerate(columns)]
    print("  ".join(c.ljust(w) for c, w in zip(columns, widths, strict=True)))
    print("  ".join("-" * w for w in widths))
    for r in text:
        print("  ".join(v.ljust(w) for v, w in zip(r, widths, strict=True)))


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        value = f"{value:.1f}" if abs(value) >= 1000 else f"{value:.4g}"
    text = str(value)
    return text if len(text) <= MAX_WIDTH else text[: MAX_WIDTH - 1] + "…"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Look at stored runs.")
    parser.add_argument("--csv", help="write the table to this CSV file instead of printing it")
    commands = parser.add_subparsers(dest="command", required=True)

    runs = commands.add_parser("runs", help="list stored runs")
    runs.add_argument("--experiment", help="only this experiment's runs")
    runs.add_argument("--last", type=int, default=30, help="how many of the newest (0 = all)")

    show = commands.add_parser("show", help="a run's settings, measures and event counts")
    show.add_argument("run", type=int)

    metrics = commands.add_parser("metrics", help="metrics over time, one column each")
    metrics.add_argument("run", type=int)
    metrics.add_argument("names", nargs="*", help="metric names (default: a few key ones)")
    metrics.add_argument("--every", type=int, default=1, help="only every Nth stored tick")

    events = commands.add_parser("events", help="a run's events")
    events.add_argument("run", type=int)
    events.add_argument("--kind", action="append", help="only these kinds (repeatable)")
    events.add_argument("--agent", help="only events involving this node id")
    events.add_argument("--from", dest="first", type=int, default=0)
    events.add_argument("--to", dest="last", type=int)
    events.add_argument("--detail", action="store_true", help="include every trade attempt")
    events.add_argument("--limit", type=int, default=200)

    agent = commands.add_parser("agent", help="one agent's life: history and coin sources")
    agent.add_argument("run", type=int)
    agent.add_argument("agent")
    agent.add_argument("--every", type=int, default=100, help="history rows every N ticks")

    sql = commands.add_parser("sql", help="any SQL query against the run database")
    sql.add_argument("query")

    args = parser.parse_args(argv)
    conn = storage.connect(load_scenario().database)

    if args.command == "runs":
        found = storage.list_runs(conn, args.experiment)
        found = found[-args.last :] if args.last else found
        keys = ["id", "scenario", "variant", "seed", "ticks", "level", "status", "experiment",
                "label", "parent_run", "branch_tick"]  # fmt: skip
        show_table([{k: run[k] for k in keys} for run in found], args.csv)
    elif args.command == "show":
        _show_run(conn, args.run)
    elif args.command == "metrics":
        names = args.names or ["population", "gini_coin", "avg_trust", "starving", "broker_share"]
        series = storage.metric_series(conn, args.run, names)
        stored = sorted({t for s in series.values() for t, _ in s})
        ticks = [t for t in stored if t == stored[0] or t % max(1, args.every) == 0]
        by_name = {name: dict(s) for name, s in series.items()}
        show_table(
            [{"tick": t, **{n: by_name.get(n, {}).get(t) for n in names}} for t in ticks], args.csv
        )
    elif args.command == "events":
        rows = storage.events(
            conn, args.run, args.first, args.last, args.agent, args.detail, args.kind, args.limit
        )
        keys = ["id", "tick", "kind", "message", "cause"]
        show_table(
            [{k: e[k] for k in keys} | {"caused_by": e["caused_by"]} for e in rows], args.csv
        )
    elif args.command == "agent":
        _show_agent(conn, args.run, args.agent, args.every, args.csv)
    elif args.command == "sql":
        cursor = conn.execute(args.query)
        columns = [d[0] for d in cursor.description or []]
        show_table([dict(zip(columns, row, strict=True)) for row in cursor.fetchall()], args.csv)


def _show_run(conn, run_id: int) -> None:
    run = storage.get_run(conn, run_id)
    if run is None:
        sys.exit(f"no run {run_id}")
    print(f"Run {run_id}")
    for key in ["scenario", "variant", "overrides", "seed", "ticks", "level", "status",
                "experiment", "label", "code_version", "parent_run", "branch_tick",
                "interventions"]:  # fmt: skip
        if run.get(key) not in (None, "", {}, []):
            print(f"  {key:<14} {run[key]}")
    scenario = load_scenario()
    measures = storage.measures(conn, run_id)
    print("\nPhenomena" + (" (from the branch tick on)" if run["branch_tick"] else ""))
    for name, spec in scenario.phenomena.items():
        if spec.measure in measures:
            verdict = "present" if spec.is_present(measures[spec.measure]) else "absent"
            print(f"  {name:<28} {verdict:<8} {spec.measure} = {measures[spec.measure]:.3f}")
    print("\nMeasures")
    for name, value in measures.items():
        print(f"  {name:<28} {value:.4f}")
    print("\nEvents by kind (detail events are stored in full-level runs only)")
    counts = storage.event_counts(conn, run_id)
    for kind, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {kind:<28} {n}")


def _show_agent(conn, run_id: int, agent_id: str, every: int, csv_path: str | None) -> None:
    lifetime = next((a for a in storage.agents(conn, run_id) if a["agent_id"] == agent_id), None)
    if lifetime is None:
        sys.exit(f"no agent {agent_id} in run {run_id}")
    print(", ".join(f"{k} {v}" for k, v in lifetime.items() if v is not None))
    print("\nLifetime coin by source (the resource ledger)")
    for row in sorted(storage.agent_totals(conn, run_id, agent_id), key=lambda r: r["amount"]):
        if row["asset"] == "coin":
            print(f"  {row['category']:<16} {row['amount']:+.1f}")
    history = storage.agent_history(conn, run_id, agent_id)
    keys = ["tick", "coin", "inventory", "community", "social_ties", "betweenness", "hunger"]
    rows = [{k: h[k] for k in keys} for h in history if h["tick"] % every == 0 or h is history[-1]]
    print("\nHistory" if rows else "\nNo per-tick history (a summary-level run)")
    if rows:
        show_table(rows, csv_path)


if __name__ == "__main__":
    main()
