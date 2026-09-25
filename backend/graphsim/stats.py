"""Plain records produced by metrics.py and communities.py, stored on the World.

Kept separate from those modules so model.py can hold them without a circular import.
"""

from dataclasses import dataclass, field

# One tick's measurements: metric name -> value, e.g. {"tick": 12, "gini_coin": 0.41, ...}.
# Per-good and per-occupation metrics are named "stock.food", "population.farmer", etc.
TickMetrics = dict[str, float]


@dataclass
class NodeStats:
    community: int  # stable community id, -1 if none
    betweenness: float  # trade-layer betweenness centrality
    degree: int  # social + trade ties


@dataclass
class CommunityRecord:
    """The life of one community (see communities.py for how identity is kept)."""

    id: int
    born: int  # tick
    parent: int | None = None  # the community it split off from, if it was born by a split
    died: int | None = None  # tick, None while alive
    fate: str = "alive"  # "alive", "merged", "split" or "dissolved"
    merged_into: int | None = None
    members: set[str] = field(default_factory=set)  # members now (or when it died)
    members_ever: set[str] = field(default_factory=set)
    peak_size: int = 0
    turnover_total: float = 0.0  # sum of (1 - Jaccard) between consecutive detections
    continuations: int = 0  # how many detections it survived
    last_seen: int = 0  # tick of the last detection it was part of

    def lifespan(self, now: int) -> int:
        return (self.died if self.died is not None else now) - self.born

    def mean_turnover(self) -> float:
        return self.turnover_total / self.continuations if self.continuations else 0.0


@dataclass
class MetricsState:
    history: list[TickMetrics] = field(default_factory=list)
    node_stats: dict[str, NodeStats] = field(default_factory=dict)
    communities: dict[int, CommunityRecord] = field(default_factory=dict)  # every one ever seen
    alive: list[int] = field(default_factory=list)  # ids of communities alive now
    community_of: dict[str, int] = field(default_factory=dict)  # agent -> community, last seen
    next_community_id: int = 0
    detections: int = 0
    # The current top trade broker. Only replaced when someone clearly overtakes them.
    top_broker: str = ""
    last_inequality_event: int = -1_000_000  # tick, for spacing out "inequality rising" events
