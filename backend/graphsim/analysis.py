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


def values(run: RunData, name: str) -> list[float]:
    return [v for _, v in run.series.get(name, [])]


def later_half(run: RunData, name: str) -> list[float]:
    """The second half of the run, after the world has had time to settle."""
    return [v for tick, v in run.series.get(name, []) if tick > run.ticks / 2]


def in_and_out_of_drought(run: RunData, name: str) -> tuple[list[float], list[float]]:
    drought = dict(run.series.get("drought", []))
    inside, outside = [], []
    for tick, value in run.series.get(name, []):
        (inside if drought.get(tick) else outside).append(value)
    return inside, outside


def ratio(a: float, b: float) -> float:
    return (a + RATIO_FLOOR) / (b + RATIO_FLOOR)


def real_communities(run: RunData) -> list[dict]:
    """Communities that lived long enough not to be detection flicker."""
    return [
        c for c in run.communities if _lifespan(c, run.ticks) >= run.min_lifespan and c["born"] > 0
    ]


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
    drought = run.series.get("drought", [])
    trust = dict(run.series.get("avg_trust", []))
    changes = []
    start_trust = None
    for (_, was), (tick, now) in zip(drought, drought[1:], strict=False):
        if now and not was:
            start_trust = trust.get(tick)
        if was and not now and start_trust is not None:
            end_trust = trust.get(tick)
            if end_trust is not None:
                changes.append(end_trust - start_trust)
    return _mean(changes)


def community_median_lifespan(run: RunData) -> float:
    lifespans = [_lifespan(c, run.ticks) for c in real_communities(run)]
    return median(lifespans) if lifespans else 0.0


def community_flicker_share(run: RunData) -> float:
    """Share of detected communities (after tick 0) that were too short-lived to be real."""
    born_later = [c for c in run.communities if c["born"] > 0]
    if not born_later:
        return 0.0
    return 1 - len(real_communities(run)) / len(born_later)


def community_turnover(run: RunData) -> float:
    """Average per-detection membership turnover of lasting communities (0 = stable)."""
    return _mean([c["mean_turnover"] for c in real_communities(run) if c["continuations"]])


def per_1000_ticks(kind: str) -> Callable[[RunData], float]:
    def measure(run: RunData) -> float:
        return 1000 * run.event_counts.get(kind, 0) / run.ticks if run.ticks else 0.0

    return measure


MEASURES: dict[str, Callable[[RunData], float]] = {
    "broker_share_ratio": broker_share_ratio,
    "broker_share": lambda run: _mean(later_half(run, "broker_share")),
    "mean_communities": lambda run: _mean(later_half(run, "communities")),
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
