"""Experiment reports: distributions across seeds, and each variant compared with the baseline.

Three views of the same stored runs:
  runs     one row per run: its measures, and whether each phenomenon is present;
  summary  per variant and measure: n, mean, median, 5th and 95th percentile, and for each
           phenomenon the share of worlds showing it with a 95% Wilson interval;
  paired   per variant and measure: the difference from the baseline run with the same seed.
           Pairing by seed compares identical starting worlds, which removes most of the
           seed-to-seed noise. We report the median difference and how consistently the
           difference points one way ("same sign" = share of seeds agreeing with the median).
"""

import csv
import json
import math
from pathlib import Path
from statistics import mean, median
from typing import Any

from graphsim import analysis, storage
from graphsim.config import Scenario

BASELINE = "baseline"


def build(conn, scenario: Scenario, experiment: str) -> dict[str, Any]:
    assignments = storage.experiment_runs(conn, experiment)
    measures_by_run = storage.all_measures(conn, [a["run_id"] for a in assignments])
    runs = []
    for a in assignments:
        measures = measures_by_run[a["run_id"]]
        present = {
            name: spec.is_present(measures[spec.measure])
            for name, spec in scenario.phenomena.items()
            if spec.measure in measures
        }
        runs.append({**a, "measures": measures, "present": present})

    labels = list(dict.fromkeys(r["label"] for r in runs))
    measure_names = sorted({m for r in runs for m in r["measures"]})
    baseline_label = _baseline_label(labels)

    summary = []
    for label in labels:
        group = [r for r in runs if r["label"] == label]
        for measure in measure_names:
            summary.append({"label": label, "measure": measure, **_describe(
                [r["measures"][measure] for r in group if measure in r["measures"]]
            )})  # fmt: skip
        for phenomenon in scenario.phenomena:
            hits = sum(r["present"].get(phenomenon, False) for r in group)
            low, high = wilson_interval(hits, len(group))
            summary.append({
                "label": label, "measure": f"present:{phenomenon}", "n": len(group),
                "mean": hits / len(group) if group else 0.0, "median": None,
                "p5": low, "p95": high,
            })  # fmt: skip

    paired = []
    if baseline_label:
        base = {r["seed"]: r for r in runs if r["label"] == baseline_label}
        for label in labels:
            if label == baseline_label:
                continue
            for measure in measure_names:
                diffs = [
                    r["measures"][measure] - base[r["seed"]]["measures"][measure]
                    for r in runs
                    if r["label"] == label
                    and r["seed"] in base
                    and measure in r["measures"]
                    and measure in base[r["seed"]]["measures"]
                ]
                paired.append({"label": label, "measure": measure, **_paired(diffs)})

    return {
        "experiment": experiment,
        "baseline": baseline_label,
        "labels": labels,
        "runs": runs,
        "summary": summary,
        "paired": paired,
    }


def reanalyze(conn, run_ids: list[int]) -> None:
    """Recomputes stored runs' measures from the database, e.g. after changing a measure's
    definition in analysis.py, without re-running anything. Summary-level runs only stored their
    metrics every few ticks, so their recomputed measures are close to, not exactly, the ones
    computed while they ran. The drought ratios suffer most (about 20% low): droughts start on
    multiples of 200, so the samples always include a drought's first, not-yet-hungry tick."""
    for run_id in run_ids:
        row = conn.execute("select ticks, config_json from runs where id = ?", (run_id,)).fetchone()
        min_lifespan = json.loads(row["config_json"])["metrics"]["community_min_lifespan"]
        data = analysis.RunData(
            series=storage.metric_series(conn, run_id),
            communities=storage.communities(conn, run_id),
            event_counts=storage.event_counts(conn, run_id),
            ticks=row["ticks"],
            min_lifespan=min_lifespan,
        )
        storage.write_batch(
            conn,
            run_id,
            storage.Batch(ticks_done=row["ticks"], measures=analysis.compute_measures(data)),
        )


def wilson_interval(hits: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% confidence interval for a proportion; sensible even for 0/n or n/n."""
    if n == 0:
        return (0.0, 0.0)
    p = hits / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    spread = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (max(0.0, centre - spread), min(1.0, centre + spread))


def percentile(values: list[float], q: float) -> float:
    """Linear-interpolated percentile, q in 0..100."""
    ordered = sorted(values)
    if not ordered:
        return float("nan")
    position = (len(ordered) - 1) * q / 100
    low, high = math.floor(position), math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def format_text(result: dict[str, Any], scenario: Scenario) -> str:
    lines = [f"\nExperiment {result['experiment']}: {len(result['runs'])} runs"]
    by_key = {(s["label"], s["measure"]): s for s in result["summary"]}
    paired_by_key = {(p["label"], p["measure"]): p for p in result["paired"]}
    for phenomenon, spec in scenario.phenomena.items():
        lines.append(f"\n{phenomenon}: {spec.description}")
        lines.append(f"  present if {spec.measure} {spec.present_if}")
        lines.append(
            f"  {'variant':<28} {'present':>13} {'95% CI':>13}  {'median':>8} {'[p5, p95]':>18}"
            f"  {'paired diff vs baseline':>26}"
        )
        for label in result["labels"]:
            presence = by_key.get((label, f"present:{phenomenon}"))
            stats = by_key.get((label, spec.measure))
            if presence is None or stats is None:
                continue
            hits = round(presence["mean"] * presence["n"])
            ci = f"[{presence['p5']:.2f}, {presence['p95']:.2f}]"
            spread = f"[{stats['p5']:.2f}, {stats['p95']:.2f}]"
            pair = paired_by_key.get((label, spec.measure))
            pair_text = (
                f"{pair['median_diff']:+.3f} ({pair['same_sign']:.0%} of {pair['n']} seeds)"
                if pair and pair["n"]
                else "n/a"
            )
            lines.append(
                f"  {label:<28} {hits:>5}/{presence['n']:<3} ({presence['mean']:4.0%}) {ci:>13}"
                f"  {stats['median']:8.3f} {spread:>18}  {pair_text:>26}"
            )
    return "\n".join(lines)


def write_csvs(result: dict[str, Any], folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    measure_names = sorted({m for r in result["runs"] for m in r["measures"]})
    phenomena = sorted({p for r in result["runs"] for p in r["present"]})
    with (folder / "runs.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["label", "seed", "run_id", *measure_names, *(f"present:{p}" for p in phenomena)]
        )
        for r in result["runs"]:
            writer.writerow([
                r["label"], r["seed"], r["run_id"],
                *(r["measures"].get(m) for m in measure_names),
                *(int(r["present"].get(p, False)) for p in phenomena),
            ])  # fmt: skip
    _write_dicts(folder / "summary.csv", result["summary"])
    _write_dicts(folder / "paired.csv", result["paired"])


def _write_dicts(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        if not rows:
            return
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _describe(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0, "mean": None, "median": None, "p5": None, "p95": None}
    return {
        "n": len(values),
        "mean": mean(values),
        "median": median(values),
        "p5": percentile(values, 5),
        "p95": percentile(values, 95),
    }


def _paired(diffs: list[float]) -> dict[str, Any]:
    if not diffs:
        return {"n": 0, "median_diff": None, "mean_diff": None, "same_sign": None}
    middle = median(diffs)
    if middle > 0:
        same_sign = sum(d > 0 for d in diffs) / len(diffs)
    elif middle < 0:
        same_sign = sum(d < 0 for d in diffs) / len(diffs)
    else:
        same_sign = sum(d == 0 for d in diffs) / len(diffs)
    return {
        "n": len(diffs),
        "median_diff": middle,
        "mean_diff": mean(diffs),
        "same_sign": same_sign,
    }


def _baseline_label(labels: list[str]) -> str | None:
    """The unswept baseline if present; otherwise the first label (e.g. in a pure sweep)."""
    if BASELINE in labels:
        return BASELINE
    return labels[0] if labels else None
