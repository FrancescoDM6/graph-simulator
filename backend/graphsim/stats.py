"""Plain records produced by metrics.py and stored on the World.

Kept separate from metrics.py so model.py can hold them without a circular import.
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
class MetricsState:
    history: list[TickMetrics] = field(default_factory=list)
    node_stats: dict[str, NodeStats] = field(default_factory=dict)
    # Community label -> member ids, from the previous tick. Used to keep labels stable.
    communities: dict[int, set[str]] = field(default_factory=dict)
    next_community_label: int = 0
    # The current top trade broker. Only replaced when someone clearly overtakes them.
    top_broker: str = ""
    last_inequality_event: int = -1_000_000  # tick, for spacing out "inequality rising" events
