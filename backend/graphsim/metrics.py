"""Tick phase 9: network measurements and structural events.

NetworkX is used only here, on throwaway graphs built from the World each tick. Metrics
describe the simulation; they never feed back into agent decisions.
"""

from statistics import mean

import networkx as nx

from graphsim.events import TIE_CHANGE_KINDS, Event, ids
from graphsim.model import Layer, World
from graphsim.stats import NodeStats, TickMetrics


def record_tick(world: World) -> None:
    social = _agent_graph(world, Layer.SOCIAL)
    trade = _agent_graph(world, Layer.TRADE)

    betweenness = nx.betweenness_centrality(trade)
    community_of = _update_communities(world, social)
    world.metrics.node_stats = {
        agent_id: NodeStats(
            community=community_of.get(agent_id, -1),
            betweenness=betweenness.get(agent_id, 0.0),
            degree=social.degree(agent_id) + trade.degree(agent_id),
        )
        for agent_id in world.agents
    }
    _update_top_broker(world, betweenness, trade)

    metrics = _tick_metrics(
        world, social, betweenness, community_count=len(world.metrics.communities)
    )
    history = world.metrics.history
    if history:
        before, after = history[-1]["social_components"], metrics["social_components"]
        _detect_component_change(world, int(before), int(after))
        _detect_inequality_jump(world, metrics["gini_coin"])
    history.append(metrics)


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
        }
    )
    return metrics


def _count_components(world: World, social: nx.Graph) -> int:
    return sum(
        1
        for component in nx.connected_components(social)
        if len(component) >= world.cfg.metrics.min_component_size
    )


# --- communities ------------------------------------------------------------------------------


def _update_communities(world: World, social: nx.Graph) -> dict[str, int]:
    """Finds communities and gives each a label that persists while its membership overlaps.

    Louvain numbers communities arbitrarily each time, so each new community takes the label of
    the previous community it overlaps most (Jaccard >= community_match_jaccard). Unmatched
    communities get a fresh label ("formed"); unmatched old labels are "dissolved".
    """
    cfg = world.cfg.metrics
    state = world.metrics
    found = [c for c in _louvain(social) if len(c) >= cfg.min_community_size]
    found.sort(key=lambda c: (-len(c), min(c)))  # biggest first, deterministic

    previous = state.communities
    labelled: dict[int, set[str]] = {}
    for members in found:
        best_label, best_overlap = None, 0.0
        for label in sorted(previous):
            if label in labelled:
                continue
            overlap = _jaccard(members, previous[label])
            if overlap > best_overlap:
                best_label, best_overlap = label, overlap
        if best_label is not None and best_overlap >= cfg.community_match_jaccard:
            labelled[best_label] = members
        else:
            label = state.next_community_label
            state.next_community_label += 1
            labelled[label] = members
            if world.tick > 1:  # everything is "new" on the first tick; don't log that
                _log_community_formed(world, label, members, social)

    for label in sorted(previous):
        if label not in labelled:
            _log_community_dissolved(world, label, previous[label])

    state.communities = labelled
    return {agent_id: label for label, members in labelled.items() for agent_id in members}


def _louvain(social: nx.Graph) -> list[set[str]]:
    # Louvain iterates over sets internally. Sets of strings iterate in an order that changes
    # between Python processes (hash randomization), so run it on integer node labels instead.
    numbered = nx.convert_node_labels_to_integers(social, label_attribute="agent_id")
    communities = nx.community.louvain_communities(numbered, weight="strength", seed=0)
    return [{numbered.nodes[n]["agent_id"] for n in c} for c in communities]


def _jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b)


def _log_community_formed(world: World, label: int, members: set[str], social: nx.Graph) -> None:
    ordered = sorted(members)
    hubs = sorted(ordered, key=lambda m: -social.degree(m))[:3]
    world.log.add(
        world.tick,
        "community_formed",
        tuple(ordered),
        f"Community {label} formed around {', '.join(world.name(h) for h in hubs)}",
        cause=f"{len(members)} agents became more tied to each other than to outsiders",
        caused_by=_tie_changes_among(world, members),
    )


def _log_community_dissolved(world: World, label: int, members: set[str]) -> None:
    still_here = sorted(m for m in members if m in world.agents)
    world.log.add(
        world.tick,
        "community_dissolved",
        tuple(still_here),
        f"Community {label} broke apart",
        cause=f"{len(members) - len(still_here)} of its {len(members)} members left the world; "
        "the rest's ties weakened or merged into other groups",
        caused_by=_tie_changes_among(world, members),
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


def _tie_changes_among(world: World, members: set[str], limit: int = 8) -> tuple[int, ...]:
    """This tick's events that added or removed ties involving the community's members."""
    changes: list[Event] = [
        e
        for e in world.log.this_tick(world.tick)
        if e.kind in TIE_CHANGE_KINDS and members & set(e.subjects)
    ]
    return ids(changes[:limit])


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
