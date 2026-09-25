"""Tick phase 9: network measurements and structural events.

NetworkX is used only here, on throwaway graphs built from the World each tick. Metrics
describe the simulation; they never feed back into agent decisions.
"""

import math
from collections import Counter
from statistics import mean

import networkx as nx

from graphsim.communities import update_communities
from graphsim.events import ids
from graphsim.model import Layer, World
from graphsim.stats import NodeStats, TickMetrics


def record_tick(world: World) -> None:
    social = _agent_graph(world, Layer.SOCIAL)
    trade = _agent_graph(world, Layer.TRADE)

    betweenness = nx.betweenness_centrality(trade)
    state = world.metrics
    if state.detections == 0 or world.tick % world.cfg.metrics.community_every == 0:
        state.community_of = update_communities(world, social)
    world.metrics.node_stats = {
        agent_id: NodeStats(
            community=state.community_of.get(agent_id, -1),
            betweenness=betweenness.get(agent_id, 0.0),
            degree=social.degree(agent_id) + trade.degree(agent_id),
        )
        for agent_id in world.agents
    }
    _update_top_broker(world, betweenness, trade)

    metrics = _tick_metrics(world, social, betweenness, community_count=len(state.alive))
    history = world.metrics.history
    if history:
        before, after = history[-1]["social_components"], metrics["social_components"]
        _detect_component_change(world, int(before), int(after))
        _detect_inequality_jump(world, metrics["gini_coin"])
    history.append(metrics)


def normalized_mutual_information(a: list, b: list) -> float:
    """How much two groupings of the same items agree: 1 = identical groupings (up to naming),
    0 = knowing one tells you nothing about the other. Arithmetic-mean normalization."""
    n = len(a)
    if n == 0:
        return 0.0
    count_a, count_b, joint = Counter(a), Counter(b), Counter(zip(a, b, strict=True))
    entropy_a = -sum(c / n * math.log(c / n) for c in count_a.values())
    entropy_b = -sum(c / n * math.log(c / n) for c in count_b.values())
    if entropy_a == 0 or entropy_b == 0:
        return 1.0 if entropy_a == entropy_b else 0.0  # one side is a single group
    mutual = sum(c / n * math.log(c * n / (count_a[x] * count_b[y])) for (x, y), c in joint.items())
    return mutual / ((entropy_a + entropy_b) / 2)


def gini(values: list[float]) -> float:
    """0 = everyone has the same, 1 = one agent has everything."""
    if not values or sum(values) <= 0:
        return 0.0
    ordered = sorted(values)
    n = len(ordered)
    weighted_sum = sum((i + 1) * v for i, v in enumerate(ordered))
    return (2 * weighted_sum) / (n * sum(ordered)) - (n + 1) / n


# --- graph construction -----------------------------------------------------------------------


def _agent_graph(world: World, layer: Layer) -> nx.Graph:
    graph = nx.Graph()
    graph.add_nodes_from(world.agents)
    for edge in world.edges.values():
        if edge.layer == layer:
            graph.add_edge(edge.a, edge.b, strength=edge.strength)
    return graph


# --- per-tick numbers -------------------------------------------------------------------------


def _tick_metrics(
    world: World, social: nx.Graph, betweenness: dict[str, float], community_count: int
) -> TickMetrics:
    """Every per-tick metric, by name. The names are what [viewer.timeline] and analysis.py use."""
    cfg = world.cfg
    agents = list(world.agents.values())
    social_ties = [e for e in world.edges.values() if e.layer == Layer.SOCIAL]
    outcomes = [i.outcome for i in world.interactions]
    brokers = [a for a in agents if cfg.is_broker(a.occupation)]
    total_betweenness = sum(betweenness.values())
    broker_betweenness = sum(betweenness.get(a.id, 0.0) for a in brokers)
    top = world.metrics.top_broker

    metrics: TickMetrics = {"tick": world.tick, "population": len(agents)}
    for occupation in cfg.occupations:
        metrics[f"population.{occupation}"] = sum(a.occupation == occupation for a in agents)
    for good in cfg.goods:
        metrics[f"stock.{good}"] = round(sum(a.inventory[good] for a in agents), 2)
        metrics[f"price.{good}"] = round(world.prices[good], 3)
    metrics.update(
        {
            "coin_total": round(sum(a.coin for a in agents), 2),
            "gini_coin": round(gini([a.coin for a in agents]), 4),
            "social_density": round(nx.density(social), 4),
            "social_components": _count_components(world, social),
            "social_clustering": round(nx.average_clustering(social), 4),
            "communities": community_count,
            "avg_trust": round(mean(e.trust for e in social_ties), 4) if social_ties else 0.0,
            "trades": outcomes.count("success"),
            "failed_trades": len(outcomes) - outcomes.count("success") - outcomes.count("gift"),
            "gifts": outcomes.count("gift"),
            "refusals": outcomes.count("refused"),
            "starving": sum(a.hunger_ticks > 0 for a in agents),
            "orgs": len(world.orgs),
            "drought": 1 if world.drought else 0,
            "top_broker_betweenness": round(betweenness.get(top, 0.0), 4),
            "broker_share": (
                round(broker_betweenness / total_betweenness, 4) if total_betweenness else 0.0
            ),
            "broker_population_share": round(len(brokers) / len(agents), 4) if agents else 0.0,
            "community_town_alignment": round(_community_town_alignment(world), 4),
        }
    )
    return metrics


def _community_town_alignment(world: World) -> float:
    """NMI between agents' communities and their home towns, over agents in a community.
    Near 1: communities just mirror geography. Lower: groups cut across towns."""
    members = [a for a in world.agents.values() if world.metrics.community_of.get(a.id, -1) >= 0]
    return normalized_mutual_information(
        [world.metrics.community_of[a.id] for a in members], [a.home for a in members]
    )


def _count_components(world: World, social: nx.Graph) -> int:
    return sum(
        1
        for component in nx.connected_components(social)
        if len(component) >= world.cfg.metrics.min_component_size
    )


# --- structural events ------------------------------------------------------------------------


def _update_top_broker(world: World, betweenness: dict[str, float], trade: nx.Graph) -> None:
    state = world.metrics
    if not betweenness:
        state.top_broker = ""
        return
    leader = max(sorted(betweenness), key=lambda a: betweenness[a])
    current = state.top_broker if state.top_broker in world.agents else ""
    cfg = world.cfg.metrics
    if leader == current or betweenness[leader] < cfg.min_broker_betweenness:
        return
    if current and betweenness[leader] < cfg.broker_overtake_margin * betweenness.get(current, 0.0):
        return
    state.top_broker = leader
    world.log.add(
        world.tick,
        "new_top_broker",
        (leader,),
        f"{world.name(leader)} became the main trade broker",
        cause=f"sits on {betweenness[leader]:.0%} of shortest trade paths, "
        f"trading with {trade.degree(leader)} partners",
        caused_by=ids(world.log.recent(leader, ("trade_started",), limit=5)),
    )


def _detect_component_change(world: World, before: int, after: int) -> None:
    if after == before:
        return
    this_tick = world.log.this_tick(world.tick)
    if after > before:
        kind, message = "network_split", f"The social network split into {after} groups"
        removals = [e for e in this_tick if e.kind in ("tie_faded", "tie_dropped", "left")]
        cause = "; ".join(e.message for e in removals[:3]) or "ties between groups faded"
        caused_by = ids(removals[:5])
    else:
        kind, message = "network_merged", f"Social groups merged ({before} → {after})"
        additions = [e for e in this_tick if e.kind in ("met", "introduced")]
        cause = "new ties bridged separate groups"
        caused_by = ids(additions[:5])
    world.log.add(world.tick, kind, (), message, cause, caused_by)


def _detect_inequality_jump(world: World, gini_now: float) -> None:
    cfg = world.cfg.metrics
    history = world.metrics.history
    if len(history) < cfg.gini_window:
        return
    if world.tick - world.metrics.last_inequality_event < cfg.gini_window:
        return
    gini_before = history[-cfg.gini_window]["gini_coin"]
    if gini_now - gini_before < cfg.gini_jump:
        return
    world.metrics.last_inequality_event = world.tick
    richest = max(world.agents.values(), key=lambda a: (a.coin, a.id))
    world.log.add(
        world.tick,
        "inequality_rising",
        (richest.id,),
        f"Inequality rose sharply (Gini {gini_before:.2f} → {gini_now:.2f})",
        cause=f"richest: {richest.name}, a {richest.occupation}, with {richest.coin:.0f} coin",
        caused_by=ids(world.log.recent(richest.id, ("trade_started",), limit=5)),
    )
