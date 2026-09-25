"""Plain records produced by metrics.py and stored on the World.

Kept separate from metrics.py so model.py can hold them without a circular import.
"""

from dataclasses import dataclass, field


@dataclass
class TickMetrics:
    tick: int
    population: int
    farmers: int
    miners: int
    merchants: int
    total_food: float
    total_coin: float
    price_food: float
    price_ore: float
    gini_coin: float
    social_density: float
    social_components: int  # connected groups of at least cfg.min_component_size agents
    social_clustering: float
    communities: int
    avg_trust: float
    trades: int
    failed_trades: int
    gifts: int
    starving: int
    orgs: int
    drought: bool
    top_broker: str  # agent id with the highest trade-layer betweenness ("" if none)
    top_broker_betweenness: float
    merchant_broker_share: float  # merchants' share of total trade-layer betweenness


@dataclass
class NodeStats:
    community: int  # stable community label, -1 if none
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
