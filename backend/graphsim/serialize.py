"""World -> JSON-ready dicts for the viewer.

The TypeScript mirror of these shapes is frontend/src/types.ts. Change both together.
"""

from dataclasses import asdict
from typing import Any

from graphsim.events import Event
from graphsim.model import Edge, Layer, World


def snapshot(world: World, events: list[Event]) -> dict[str, Any]:
    history = world.metrics.history
    return {
        "tick": world.tick,
        "seed": world.seed,
        "drought": world.drought,
        "prices": {good: round(price, 3) for good, price in world.prices.items()},
        "nodes": _nodes(world),
        "edges": [edge_dict(e) for e in world.edges.values()],
        "metrics": asdict(history[-1]) if history else None,
        "events": [event_dict(e) for e in events],
    }


def event_dict(event: Event) -> dict[str, Any]:
    return {
        "tick": event.tick,
        "kind": event.kind,
        "subjects": list(event.subjects),
        "message": event.message,
        "cause": event.cause,
    }


def edge_dict(edge: Edge) -> dict[str, Any]:
    return {
        "id": f"{edge.a}|{edge.b}|{edge.layer}",
        "source": edge.a,
        "target": edge.b,
        "layer": str(edge.layer),
        "strength": round(edge.strength, 3),
        "trust": round(edge.trust, 3) if edge.layer == Layer.SOCIAL else None,
        "created": edge.created,
        "last_active": edge.last_active,
    }


def _nodes(world: World) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for agent in world.agents.values():
        stats = world.metrics.node_stats.get(agent.id)
        nodes.append(
            {
                "id": agent.id,
                "kind": "agent",
                "name": agent.name,
                "occupation": str(agent.occupation),
                "home": agent.home,
                "food": round(agent.food, 2),
                "ore": round(agent.ore, 2),
                "coin": round(agent.coin, 2),
                "hunger_ticks": agent.hunger_ticks,
                "need": agent.need,
                "org": world.org_of(agent.id),
                "arrived": agent.arrived,
                "community": stats.community if stats else -1,
                "betweenness": round(stats.betweenness, 4) if stats else 0.0,
                "degree": stats.degree if stats else 0,
            }
        )
    for town in world.towns.values():
        nodes.append(
            {
                "id": town.id,
                "kind": "town",
                "name": town.name,
                "residents": len(world.agents_in_town(town.id)),
            }
        )
    for site in world.sites.values():
        nodes.append(
            {
                "id": site.id,
                "kind": "site",
                "name": site.name,
                "site_kind": str(site.kind),
                "stock": round(site.stock, 1),
                "capacity": site.capacity,
            }
        )
    for org in world.orgs.values():
        nodes.append(
            {
                "id": org.id,
                "kind": "org",
                "name": org.name,
                "home": org.home,
                "founded": org.founded,
                "members": len(world.members_of(org.id)),
            }
        )
    return nodes
