"""Milestones: turning points in an agent's life, explained from the resource ledger.

An agent reaches a milestone when its standing changes and stays changed for `status_hold` ticks:

  wealthy   holding at least `wealthy_ratio` times the median agent's coin,
  poor      holding at most `poor_ratio` times the median agent's coin,
  hub       having at least `hub_ratio` times the median agent's number of ties,

which gives the events became_wealthy / no_longer_wealthy, became_poor / no_longer_poor and
became_hub / no_longer_hub. Ratios to the median (not ranks) mean nobody "becomes wealthy"
while everyone still holds the same.

Each milestone's cause is a summary of the agent's ledger over the last `attribution_window`
ticks ("earned 210 coin: commission 71% from 14 pairs, ..."), and its caused_by points at the
largest ledger entries behind it: recorded trades and gifts, never guesses. This runs in the
metrics phase and only reads the world, so it cannot change what happens.
"""

from statistics import median

from graphsim.events import ids
from graphsim.model import Flow, Layer, World

STATUSES = ("wealthy", "poor", "hub")


def update_milestones(world: World) -> None:
    state, cfg = world.metrics, world.cfg.metrics
    state.recent_flows.append(list(world.flows))
    del state.recent_flows[: -cfg.attribution_window]
    for key in [k for k in state.statuses if k[0] not in world.agents]:
        del state.statuses[key]  # agents who left take their standing with them
    agents = list(world.agents.values())
    if not agents:
        return

    median_coin = median(a.coin for a in agents)
    degree = {
        a.id: len(world.edges_of(a.id, Layer.SOCIAL)) + len(world.edges_of(a.id, Layer.TRADE))
        for a in agents
    }
    median_degree = median(degree.values())
    for agent in agents:
        standing = {
            "wealthy": median_coin > 0 and agent.coin >= cfg.wealthy_ratio * median_coin,
            "poor": median_coin > 0 and agent.coin <= cfg.poor_ratio * median_coin,
            "hub": median_degree > 0 and degree[agent.id] >= cfg.hub_ratio * median_degree,
        }
        for status in STATUSES:
            _track(world, agent.id, status, standing[status])


def _track(world: World, agent_id: str, status: str, is_now: bool) -> None:
    """Counts how long a change in standing has lasted; logs it once it has lasted long enough."""
    state = world.metrics
    key = (agent_id, status)
    had = key in state.statuses
    if is_now == had:
        state.streaks.pop(key, None)
        return
    streak = state.streaks.get(key, 0) + 1
    if streak < world.cfg.metrics.status_hold:
        state.streaks[key] = streak
        return
    state.streaks.pop(key)
    if is_now:
        state.statuses[key] = None
        kind = f"became_{status}"
    else:
        del state.statuses[key]
        kind = f"no_longer_{status}"
    cause, caused_by = _explain(world, agent_id, status, is_now)
    name = world.name(agent_id)
    message = f"{name} became {status}" if is_now else f"{name} is no longer {status}"
    world.log.add(world.tick, kind, (agent_id,), message, cause, caused_by)


def _explain(world: World, agent_id: str, status: str, is_now: bool) -> tuple[str, tuple[int, ...]]:
    if status == "hub":
        social = len(world.edges_of(agent_id, Layer.SOCIAL))
        trade = len(world.edges_of(agent_id, Layer.TRADE))
        recent = world.log.recent(agent_id, ("trade_started", "met", "introduced"), limit=5)
        return f"{social} social and {trade} trade ties", ids(recent)

    window = world.cfg.metrics.attribution_window
    coin = [
        f
        for tick_flows in world.metrics.recent_flows
        for f in tick_flows
        if f.agent == agent_id and f.asset == "coin" and f.category != "endowment"
    ]
    income = [f for f in coin if f.amount > 0]
    spending = [f for f in coin if f.amount < 0]
    cause = (
        f"last {window} ticks: earned {sum(f.amount for f in income):.0f} coin"
        f"{_breakdown(income)}; spent {-sum(f.amount for f in spending):.0f}{_breakdown(spending)}"
    )
    # Point at the largest entries on the side that explains the change.
    explains_rise = (status == "wealthy") == is_now
    side = income if explains_rise else spending
    largest = sorted((f for f in side if f.event_id >= 0), key=lambda f: -abs(f.amount))
    return cause, tuple(dict.fromkeys(f.event_id for f in largest))[:3]


def _breakdown(flows: list[Flow]) -> str:
    """' (commission 71% from 14 pairs, sale 20%, levy_received 9%)'"""
    total = sum(abs(f.amount) for f in flows)
    if not total:
        return ""
    by_category: dict[str, list[Flow]] = {}
    for flow in flows:
        by_category.setdefault(flow.category, []).append(flow)
    parts = []
    for category, entries in sorted(
        by_category.items(), key=lambda kv: -sum(abs(f.amount) for f in kv[1])
    ):
        share = sum(abs(f.amount) for f in entries) / total
        if share < 0.01:
            continue  # rounding noise, e.g. a levy on a balance of almost nothing
        partners = len({f.counterparty for f in entries if f.counterparty})
        noun = "pairs" if category == "commission" else "partners"
        parts.append(f"{category} {share:.0%}" + (f" from {partners} {noun}" if partners else ""))
    return " (" + ", ".join(parts) + ")"
