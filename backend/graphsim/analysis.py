"""Run-level measures: one number per run for each question we ask of a world.

Each measure is a small function of a run's stored data (metric series, community records,
event counts), so measures can be recomputed from the database at any time, e.g. after you
change a definition, without re-running anything. scenario.toml [phenomena] turns measures into
yes/no "is the phenomenon present?" answers.

To add a measure: write a function below that takes RunData and returns a float, and add it to
MEASURES. It then appears in experiment reports and the viewer automatically.
"""

from collections.abc import Callable
from dataclasses import dataclass
from statistics import mean, median

from graphsim.stats import CommunityRecord

Series = list[tuple[int, float]]  # [(tick, value), ...] in tick order
RATIO_FLOOR = 0.1  # added to both sides of ratios so near-zero baselines don't explode


@dataclass
class RunData:
    series: dict[str, Series]  # metric name -> series (possibly sampled every few ticks)
    communities: list[dict]  # rows as in the communities table (see community_row)
    event_counts: dict[str, int]
    ticks: int
    min_lifespan: int  # communities shorter-lived than this count as detection flicker
    # A branch (runner.branch) is measured from its branch point on: what happened after the
    # intervention. None for an ordinary run, which is measured over the whole run (and its
    # averages over the second half, once the world has settled).
    branch_tick: int | None = None


def ledger_summary(flows: list[dict]) -> dict:
    """Ledger entries (as stored) summed by asset and category, plus the counterparties that
    account for the most coin, e.g. to show where an agent's wealth came from."""
    by_category: dict[str, dict[str, float]] = {}
    by_counterparty: dict[tuple[str, str], float] = {}
    for flow in flows:
        per_asset = by_category.setdefault(flow["asset"], {})
        per_asset[flow["category"]] = per_asset.get(flow["category"], 0.0) + flow["amount"]
        if flow["asset"] == "coin" and flow["counterparty"]:
            key = (flow["counterparty"], flow["category"])
            by_counterparty[key] = by_counterparty.get(key, 0.0) + flow["amount"]
    top = sorted(by_counterparty.items(), key=lambda kv: -abs(kv[1]))[:12]
    return {
        "by_category": {
            asset: {c: round(v, 4) for c, v in categories.items()}
            for asset, categories in by_category.items()
        },
        "counterparties": [
            {"counterparty": who, "category": category, "coin": round(amount, 4)}
            for (who, category), amount in top
        ],
    }


def compute_measures(run: RunData) -> dict[str, float]:
    return {name: round(float(measure(run)), 6) for name, measure in MEASURES.items()}


def community_row(record: CommunityRecord, now: int) -> dict:
    """A community record as a plain row (the shape of the communities table)."""
    return {
        "community_id": record.id,
        "born": record.born,
        "died": record.died,
        "fate": record.fate,
        "parent": record.parent,
        "merged_into": record.merged_into,
        "peak_size": record.peak_size,
        "members_ever": len(record.members_ever),
        "mean_turnover": round(record.mean_turnover(), 4),
        "continuations": record.continuations,
        "lifespan": record.lifespan(now),
    }


# --- helpers ----------------------------------------------------------------------------------


def window(run: RunData, name: str) -> Series:
    """The part of a series that measures look at: all of it, or a branch's part."""
    series = run.series.get(name, [])
    return (
        series if run.branch_tick is None else [(t, v) for t, v in series if t >= run.branch_tick]
    )


def values(run: RunData, name: str) -> list[float]:
    return [v for _, v in window(run, name)]


def later_half(run: RunData, name: str) -> list[float]:
    """Where averages are taken: the second half of the run, after the world has had time to
    settle; for a branch, everything from its branch point."""
    if run.branch_tick is not None:
        return values(run, name)
    return [v for tick, v in run.series.get(name, []) if tick > run.ticks / 2]


def window_length(run: RunData) -> int:
    return run.ticks - (run.branch_tick - 1 if run.branch_tick is not None else 0)


def in_and_out_of_drought(run: RunData, name: str) -> tuple[list[float], list[float]]:
    drought = dict(window(run, "drought"))
    inside, outside = [], []
    for tick, value in window(run, name):
        (inside if drought.get(tick) else outside).append(value)
    return inside, outside


def ratio(a: float, b: float) -> float:
    return (a + RATIO_FLOOR) / (b + RATIO_FLOOR)


def born_later(run: RunData) -> list[dict]:
    """Communities that formed during the run (not the ones found at the first detection); for
    a branch, those formed after its branch point."""
    if run.branch_tick is not None:
        return [c for c in run.communities if c["born"] >= run.branch_tick]
    if not run.communities:
        return []
    first_detection = min(c["born"] for c in run.communities)
    return [c for c in run.communities if c["born"] > first_detection]


def real_communities(run: RunData) -> list[dict]:
    """Communities formed during the run that lived long enough not to be detection flicker."""
    return [c for c in born_later(run) if _lifespan(c, run.ticks) >= run.min_lifespan]


def _lifespan(community: dict, now: int) -> int:
    died = community["died"] if community["died"] is not None else now
    return died - community["born"]


def _mean(xs: list[float]) -> float:
    return mean(xs) if xs else 0.0


# --- the measures -----------------------------------------------------------------------------


def broker_share_ratio(run: RunData) -> float:
    """How much more trade betweenness brokers hold than their share of the population."""
    population_share = _mean(later_half(run, "broker_population_share"))
    return _mean(later_half(run, "broker_share")) / population_share if population_share else 0.0


def drought_starvation_ratio(run: RunData) -> float:
    inside, outside = in_and_out_of_drought(run, "starving")
    return ratio(_mean(inside), _mean(outside)) if inside else 1.0


def drought_gift_ratio(run: RunData) -> float:
    inside, outside = in_and_out_of_drought(run, "gifts")
    return ratio(_mean(inside), _mean(outside)) if inside else 1.0


def drought_trust_change(run: RunData) -> float:
    """Average trust at each drought's last tick minus just before it began."""
    drought = window(run, "drought")
    trust = dict(run.series.get("avg_trust", []))
    changes = []
    start_trust = None
    for (previous_tick, was), (_, now) in zip(drought, drought[1:], strict=False):
        if now and not was:  # previous_tick is the last one before the drought
            start_trust = trust.get(previous_tick)
        if was and not now and start_trust is not None:  # previous_tick is its last drought tick
            end_trust = trust.get(previous_tick)
            if end_trust is not None:
                changes.append(end_trust - start_trust)
    return _mean(changes)


def community_median_lifespan(run: RunData) -> float:
    lifespans = [_lifespan(c, run.ticks) for c in real_communities(run)]
    return median(lifespans) if lifespans else 0.0


def community_flicker_share(run: RunData) -> float:
    """Share of communities formed during the run that were too short-lived to be real."""
    formed = born_later(run)
    return 1 - len(real_communities(run)) / len(formed) if formed else 0.0


def community_turnover(run: RunData) -> float:
    """Average per-detection membership turnover of lasting communities (0 = stable)."""
    return _mean([c["mean_turnover"] for c in real_communities(run) if c["continuations"]])


def per_1000_ticks(kind: str) -> Callable[[RunData], float]:
    def measure(run: RunData) -> float:
        length = window_length(run)
        return 1000 * run.event_counts.get(kind, 0) / length if length > 0 else 0.0

    return measure


MEASURES: dict[str, Callable[[RunData], float]] = {
    "broker_share_ratio": broker_share_ratio,
    "broker_share": lambda run: _mean(later_half(run, "broker_share")),
    "mean_communities": lambda run: _mean(later_half(run, "communities")),
    # Separate social groups (of at least min_component_size): 1 = one connected society.
    "mean_components": lambda run: _mean(later_half(run, "social_components")),
    # 1 = communities just mirror the towns; lower = groups that cut across towns.
    "mean_town_alignment": lambda run: _mean(later_half(run, "community_town_alignment")),
    "community_median_lifespan": community_median_lifespan,
    "community_turnover": community_turnover,
    "community_flicker_share": community_flicker_share,
    "splits_per_1000": per_1000_ticks("community_split"),
    "mergers_per_1000": per_1000_ticks("community_merged"),
    "gini_final": lambda run: values(run, "gini_coin")[-1] if values(run, "gini_coin") else 0.0,
    "gini_rise": lambda run: (
        values(run, "gini_coin")[-1] - values(run, "gini_coin")[0]
        if values(run, "gini_coin")
        else 0.0
    ),
    "drought_starvation_ratio": drought_starvation_ratio,
    "drought_gift_ratio": drought_gift_ratio,
    "drought_trust_change": drought_trust_change,
    "mean_trust": lambda run: _mean(later_half(run, "avg_trust")),
    "mean_clustering": lambda run: _mean(later_half(run, "social_clustering")),
    "mean_density": lambda run: _mean(later_half(run, "social_density")),
    "min_population_ratio": lambda run: (
        min(values(run, "population")) / values(run, "population")[0]
        if values(run, "population")
        else 0.0
    ),
    "departures_per_1000": per_1000_ticks("left"),
    "gifts_per_1000": per_1000_ticks("gift"),
}
