"""The world: nodes, edges, and the few helpers the rules need to read and change them.

Edges are keyed by (a, b, layer) with a < b, so two nodes can be linked on several layers at
once (a multiplex graph). All containers are insertion-ordered dicts, never sets, so iterating
them is deterministic for a given seed.
"""

import random
from dataclasses import dataclass, field
from enum import StrEnum

from graphsim.config import SimConfig
from graphsim.events import EventLog
from graphsim.stats import MetricsState


class Layer(StrEnum):
    SOCIAL = "social"
    TRADE = "trade"
    MEMBERSHIP = "membership"
    ACCESS = "access"


# --- Nodes -----------------------------------------------------------------------------------


@dataclass
class Agent:
    id: str
    name: str
    occupation: str  # a key of cfg.occupations
    home: str  # town id
    inventory: dict[str, float]  # good -> amount held, for every good in cfg.goods
    coin: float
    hunger_ticks: int = 0
    need: str = ""  # the most pressing good to buy this tick, or ""
    arrived: int = 0  # tick the agent entered the world


@dataclass
class Town:
    id: str
    name: str
    founding_mix: dict[str, int]  # occupation -> how many the town started with


@dataclass
class Site:
    id: str
    name: str
    kind: str  # a key of cfg.site_kinds
    stock: float
    capacity: float
    regen: float  # stock regained per tick (before drought effects)


@dataclass
class Org:
    id: str
    name: str
    home: str  # town id of the founder
    founded: int  # tick


# --- Edges -----------------------------------------------------------------------------------

EdgeKey = tuple[str, str, Layer]


def edge_key(a: str, b: str, layer: Layer) -> EdgeKey:
    return (a, b, layer) if a < b else (b, a, layer)


@dataclass
class Edge:
    a: str
    b: str
    layer: Layer
    strength: float = 0.5  # social/trade: how strong or active the tie is (0..1)
    trust: float = 0.5  # social only (0..1)
    cost: float = 1.0  # access only: travel cost
    created: int = 0  # tick
    last_active: int = 0  # tick of the most recent interaction

    @property
    def key(self) -> EdgeKey:
        return (self.a, self.b, self.layer)

    def other(self, node_id: str) -> str:
        return self.b if node_id == self.a else self.a


@dataclass
class Interaction:
    """One trade attempt this tick. Recorded by trade.py, applied by relationships.py."""

    buyer: str
    seller: str
    good: str  # a key of cfg.goods
    amount: float
    outcome: str  # "success", "gift", "refused", "no_surplus" or "cannot_afford"
    cause: str  # human-readable explanation
    broker: str | None = None  # broker who connected buyer and seller, if any
    event_id: int = -1  # the event logged for this attempt
    price: float = 0.0  # per unit, as paid by the buyer (successful trades only)
    commission: float = 0.0  # per unit, the broker's part of the price


# Why an agent's holdings changed. Every change to coin or goods is exactly one of these.
FLOW_CATEGORIES = (
    "endowment",  # what an agent starts with (or brings when arriving)
    "harvest",
    "tool_use",
    "eaten",
    "spoiled",
    "sale",
    "purchase",
    "commission",  # a broker's cut of a trade it connected
    "gift_given",
    "gift_received",
    "levy_paid",
    "levy_received",
    "departure",  # holdings that leave the world with an agent
)


@dataclass
class Flow:
    """One entry in the resource ledger: `amount` of an asset entering (+) or leaving (-) an
    agent's holdings, and why. The ledger is complete: an agent's flows in a tick add up to the
    change in its holdings (tested in test_ledger.py)."""

    agent: str
    asset: str  # "coin" or a good
    amount: float
    category: str  # one of FLOW_CATEGORIES
    counterparty: str = ""  # the other agent; for a commission, "buyer>seller"
    event_id: int = -1  # the trade or gift event, if any


@dataclass
class TrustChange:
    """One entry in the trust ledger: every change to a tie's trust, and the event behind it."""

    a: str
    b: str
    before: float
    after: float
    event_id: int  # the interaction (trade, gift, refusal) that changed it


# --- World -----------------------------------------------------------------------------------


@dataclass
class World:
    cfg: SimConfig
    seed: int
    rng: random.Random
    log: EventLog = field(default_factory=EventLog)
    tick: int = 0
    drought: bool = False
    drought_event: int | None = None  # id of the current drought's "drought_started" event
    prices: dict[str, float] = field(default_factory=dict)  # good -> current base price
    # good -> price at the last "price rose/fell" event, so only big moves get logged
    logged_prices: dict[str, float] = field(default_factory=dict)

    agents: dict[str, Agent] = field(default_factory=dict)
    towns: dict[str, Town] = field(default_factory=dict)
    sites: dict[str, Site] = field(default_factory=dict)
    orgs: dict[str, Org] = field(default_factory=dict)
    edges: dict[EdgeKey, Edge] = field(default_factory=dict)

    interactions: list[Interaction] = field(default_factory=list)  # this tick only
    trust_changes: list[TrustChange] = field(default_factory=list)  # this tick only
    flows: list[Flow] = field(default_factory=list)  # this tick only (the resource ledger)
    metrics: MetricsState = field(default_factory=MetricsState)

    # node id -> keys of the edges touching it. A dict used as an insertion-ordered set.
    _adjacent: dict[str, dict[EdgeKey, None]] = field(default_factory=dict)
    _id_counters: dict[str, int] = field(default_factory=dict)
    # Every agent name ever given out, so a newcomer never shares a name with someone who left.
    used_names: set[str] = field(default_factory=set)

    # --- ids and names ---

    def new_id(self, prefix: str) -> str:
        """Returns ids like "agent-007". Ids are never reused, even after a node is removed."""
        n = self._id_counters.get(prefix, 0) + 1
        self._id_counters[prefix] = n
        return f"{prefix}-{n:03d}"

    def name(self, node_id: str) -> str:
        for nodes in (self.agents, self.towns, self.sites, self.orgs):
            if node_id in nodes:
                return nodes[node_id].name
        return node_id

    # --- nodes ---

    def add_agent(self, agent: Agent) -> None:
        self.agents[agent.id] = agent
        self._adjacent[agent.id] = {}

    def add_town(self, town: Town) -> None:
        self.towns[town.id] = town
        self._adjacent[town.id] = {}

    def add_site(self, site: Site) -> None:
        self.sites[site.id] = site
        self._adjacent[site.id] = {}

    def add_org(self, org: Org) -> None:
        self.orgs[org.id] = org
        self._adjacent[org.id] = {}

    def remove_node(self, node_id: str) -> None:
        for key in list(self._adjacent.get(node_id, {})):
            self.remove_edge(key)
        self._adjacent.pop(node_id, None)
        for nodes in (self.agents, self.towns, self.sites, self.orgs):
            nodes.pop(node_id, None)

    # --- edges ---

    def get_edge(self, a: str, b: str, layer: Layer) -> Edge | None:
        return self.edges.get(edge_key(a, b, layer))

    def add_edge(self, a: str, b: str, layer: Layer, **fields: float) -> Edge:
        """Creates the edge (or returns the existing one unchanged)."""
        key = edge_key(a, b, layer)
        if key in self.edges:
            return self.edges[key]
        edge = Edge(key[0], key[1], layer, created=self.tick, last_active=self.tick, **fields)
        self.edges[key] = edge
        self._adjacent[key[0]][key] = None
        self._adjacent[key[1]][key] = None
        return edge

    def remove_edge(self, key: EdgeKey) -> None:
        self.edges.pop(key, None)
        self._adjacent.get(key[0], {}).pop(key, None)
        self._adjacent.get(key[1], {}).pop(key, None)

    def edges_of(self, node_id: str, layer: Layer | None = None) -> list[Edge]:
        keys = self._adjacent.get(node_id, {})
        return [self.edges[k] for k in keys if layer is None or k[2] == layer]

    def neighbors(self, node_id: str, layer: Layer | None = None) -> list[str]:
        return [edge.other(node_id) for edge in self.edges_of(node_id, layer)]

    def record_flow(
        self,
        agent: str,
        asset: str,
        amount: float,
        category: str,
        counterparty: str = "",
        event_id: int = -1,
    ) -> None:
        """Adds a ledger entry (zero amounts are skipped)."""
        if amount != 0:
            self.flows.append(Flow(agent, asset, amount, category, counterparty, event_id))

    # --- common questions the rules ask ---

    def org_of(self, agent_id: str) -> str | None:
        orgs = self.neighbors(agent_id, Layer.MEMBERSHIP)
        return orgs[0] if orgs else None

    def members_of(self, org_id: str) -> list[str]:
        return self.neighbors(org_id, Layer.MEMBERSHIP)

    def trust(self, a: str, b: str) -> float | None:
        """Trust between two agents, or None if they have no social tie."""
        tie = self.get_edge(a, b, Layer.SOCIAL)
        return tie.trust if tie else None

    def agents_in_town(self, town_id: str) -> list[str]:
        """Agents who live in the town."""
        return [a.id for a in self.agents.values() if a.home == town_id]

    def agents_present_in(self, town_id: str) -> list[str]:
        """Agents with access to the town: its residents plus merchants who visit it."""
        return [n for n in self.neighbors(town_id, Layer.ACCESS) if n in self.agents]

    def towns_reachable_by(self, agent_id: str) -> list[str]:
        return [n for n in self.neighbors(agent_id, Layer.ACCESS) if n in self.towns]
