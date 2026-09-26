"""Interventions: changes made to a running world from outside, at a chosen tick.

An intervention is data, e.g. {"tick": 1000, "kind": "remove_agent", "target": "top_broker"}.
A run's interventions are its `world.schedule`; `apply_due` runs at the start of every tick and
applies the ones due, before anything else happens that tick. With nothing scheduled it does
nothing at all (and draws no random numbers), so ordinary runs are unaffected.

Targets are a node id ("agent-012") or a rule resolved at that tick, so the same intervention
can be applied to every seed of an experiment (agent ids and names differ between seeds):

    top_broker  richest  poorest  most_connected     one agent
    starving                                         every starving agent
    occupation:<name>                                every agent in the occupation
    town:<name>  site:<name>                         a place, by name
    strongest_tie_of:<target>                        that agent's closest friend

Every intervention logs an "intervention" event; what it directly causes (an agent leaving, a
drought starting) cites it. Coin and goods it adds or removes are ledger flows, so the ledger
still accounts for every change in holdings.
"""

import random
from typing import Any

from graphsim.config import ScenarioError, with_setting
from graphsim.model import Agent, Layer, Org, Site, TrustChange, World
from graphsim.rules.needs import _leave


class InterventionError(ValueError):
    """An intervention that can't be understood (unknown kind, missing or wrong parameters)."""


Number = (int, float)

# kind -> the parameters it takes, with their types. "tick" and "kind" are always required.
KINDS: dict[str, dict[str, type | tuple[type, ...]]] = {
    # shocks
    "remove_agent": {"target": str},
    "start_drought": {"length": int},
    "end_drought": {},
    # economy
    "give": {"target": str, "asset": str, "amount": Number},
    "subsidize": {"occupation": str, "coin": Number, "ticks": int},
    "set": {"setting": str, "value": (int, float, bool, str)},
    # geography
    "add_road": {"between": list},
    "remove_road": {"between": list},
    "add_site": {"town": str, "site_kind": str, "scale": Number},
    "remove_site": {"target": str},
    # social
    "link": {"between": list, "layer": str, "strength": Number, "trust": Number},
    "sever": {"between": list, "layer": str},
    "set_trust": {"between": list, "value": Number},
    "found_org": {"members": list},
    # control
    "reseed": {},
}


def validate(spec: dict[str, Any]) -> dict[str, Any]:
    """Checks an intervention's kind and parameters (not its targets, which are only known at
    its tick). Returns it unchanged, or raises InterventionError naming the problem."""
    kind = spec.get("kind")
    if kind not in KINDS:
        raise InterventionError(f"unknown intervention kind {kind!r}; known: {list(KINDS)}")
    if not isinstance(spec.get("tick"), int) or spec["tick"] < 1:
        raise InterventionError(f"{kind}: needs a whole-number tick of at least 1")
    expected = KINDS[kind]
    given = {k for k in spec if k not in ("tick", "kind")}
    if given != set(expected):
        raise InterventionError(f"{kind}: takes {sorted(expected)}, got {sorted(given)}")
    for key, kinds in expected.items():
        if not isinstance(spec[key], kinds):
            raise InterventionError(f"{kind}.{key}: wrong type ({spec[key]!r})")
    if "between" in expected and len(spec["between"]) != 2:
        raise InterventionError(f"{kind}.between: needs exactly two targets")
    if "layer" in expected and spec["layer"] not in ("social", "trade"):
        raise InterventionError(f'{kind}.layer: "social" or "trade"')
    return spec


def schedule(world: World, specs: list[dict[str, Any]]) -> None:
    """Adds interventions to the world's schedule (they run when their tick comes)."""
    world.schedule.extend(validate(dict(spec)) for spec in specs)
    world.schedule.sort(key=lambda s: s["tick"])  # stable: same-tick ones keep their order


def apply_due(world: World) -> None:
    """Called at the start of every tick: applies the interventions due now, then pays any
    running subsidies."""
    while world.schedule and world.schedule[0]["tick"] <= world.tick:
        spec = world.schedule.pop(0)
        APPLY[spec["kind"]](world, spec)
    for subsidy in list(world.subsidies):
        occupation, coin, until, event_id = subsidy
        if world.tick > until:
            world.subsidies.remove(subsidy)
            continue
        for agent in list(world.agents.values()):
            if agent.occupation == occupation:
                agent.coin += coin
                world.record_flow(agent.id, "coin", coin, "subsidy", event_id=event_id)


# --- Targets -------------------------------------------------------------------------------------


def resolve(world: World, target: str) -> list[str]:
    """The node ids a target names at this tick (possibly none)."""
    agents = list(world.agents.values())
    for nodes in (world.agents, world.towns, world.sites, world.orgs):
        if target in nodes:
            return [target]
    if target == "top_broker":
        return [world.metrics.top_broker] if world.metrics.top_broker in world.agents else []
    if target in ("richest", "poorest"):
        pick = max if target == "richest" else min
        return [pick(agents, key=lambda a: a.coin).id] if agents else []
    if target == "most_connected":
        return [max(agents, key=lambda a: _degree(world, a)).id] if agents else []
    if target == "starving":
        return [a.id for a in agents if a.hunger_ticks > 0]
    prefix, _, name = target.partition(":")
    if prefix == "occupation":
        return [a.id for a in agents if a.occupation == name]
    if prefix in ("town", "site"):
        nodes = world.towns if prefix == "town" else world.sites
        return [node.id for node in nodes.values() if node.name == name]
    if prefix == "strongest_tie_of":
        of = resolve(world, name)
        ties = world.edges_of(of[0], Layer.SOCIAL) if of else []
        return [max(ties, key=lambda t: t.strength).other(of[0])] if ties else []
    raise InterventionError(f"unknown target {target!r}")


def _degree(world: World, agent: Agent) -> int:
    return len(world.edges_of(agent.id, Layer.SOCIAL)) + len(world.edges_of(agent.id, Layer.TRADE))


def _one(world: World, target: str) -> str | None:
    found = resolve(world, target)
    return found[0] if found else None


def _pair(world: World, spec: dict[str, Any]) -> tuple[str, str] | None:
    a, b = (_one(world, t) for t in spec["between"])
    return (a, b) if a and b and a != b else None


def _log(world: World, spec: dict[str, Any], subjects: tuple[str, ...], message: str) -> int:
    cause = f"intervention: {spec['kind']}"
    return world.log.add(world.tick, "intervention", subjects, message, cause=cause).id


def _skipped(world: World, spec: dict[str, Any], why: str) -> None:
    _log(world, spec, (), f"Intervention skipped ({spec['kind']}): {why}")


# --- Shocks --------------------------------------------------------------------------------------


def _remove_agent(world: World, spec: dict[str, Any]) -> None:
    targets = [t for t in resolve(world, spec["target"]) if t in world.agents]
    if not targets:
        return _skipped(world, spec, f"no agent matches {spec['target']!r}")
    for agent_id in targets:
        agent = world.agents[agent_id]
        message = f"Intervention: {agent.name} was removed from the world"
        event_id = _log(world, spec, (agent_id,), message)
        _leave(world, agent, "removed by an intervention", (event_id,))


def _start_drought(world: World, spec: dict[str, Any]) -> None:
    world.forced_drought_until = world.tick + spec["length"] - 1
    message = f"Intervention: a drought of {spec['length']} ticks"
    world.drought_intervention = _log(world, spec, (), message)


def _end_drought(world: World, spec: dict[str, Any]) -> None:
    """Rain now: no drought until this dry season would have ended anyway."""
    seasons = world.cfg.seasons
    season_start = world.tick - world.tick % seasons.drought_every
    world.forced_drought_until = -1
    world.drought_suppressed_until = season_start + seasons.drought_length - 1
    world.drought_intervention = _log(world, spec, (), "Intervention: the drought was ended")


# --- Economy -------------------------------------------------------------------------------------


def _give(world: World, spec: dict[str, Any]) -> None:
    """Adds (or, with a negative amount, takes) coin or a good; never below zero."""
    asset, amount = spec["asset"], float(spec["amount"])
    if asset != "coin" and asset not in world.cfg.goods:
        raise InterventionError(f"give.asset: no good called {asset!r}")
    targets = [t for t in resolve(world, spec["target"]) if t in world.agents]
    if not targets:
        return _skipped(world, spec, f"no agent matches {spec['target']!r}")
    names = ", ".join(world.name(t) for t in targets)
    event_id = _log(world, spec, tuple(targets), f"Intervention: {names} got {amount:g} {asset}")
    for agent_id in targets:
        agent = world.agents[agent_id]
        held = agent.coin if asset == "coin" else agent.inventory[asset]
        change = max(amount, -held)
        if asset == "coin":
            agent.coin += change
        else:
            agent.inventory[asset] += change
        world.record_flow(agent_id, asset, change, "intervention", event_id=event_id)


def _subsidize(world: World, spec: dict[str, Any]) -> None:
    occupation, coin, ticks = spec["occupation"], float(spec["coin"]), spec["ticks"]
    if occupation not in world.cfg.occupations:
        raise InterventionError(f"subsidize.occupation: no occupation {occupation!r}")
    message = f"Intervention: every {occupation} gets {coin:g} coin a tick for {ticks} ticks"
    event_id = _log(world, spec, (), message)
    world.subsidies.append((occupation, coin, world.tick + ticks - 1, event_id))


def _set(world: World, spec: dict[str, Any]) -> None:
    try:
        world.cfg = with_setting(world.cfg, spec["setting"], spec["value"])
    except ScenarioError as error:
        raise InterventionError(str(error)) from error
    _log(world, spec, (), f"Intervention: {spec['setting']} set to {spec['value']}")


# --- Geography -----------------------------------------------------------------------------------


def _road_ends(world: World, spec: dict[str, Any]) -> tuple[str, str] | None:
    pair = _pair(world, spec)
    return pair if pair and all(end in world.towns for end in pair) else None


def _reaches_neighbours(world: World, agent_id: str) -> bool:
    occupation = world.agents[agent_id].occupation
    return world.cfg.occupations[occupation].reach == "home_and_neighbours"


def _add_road(world: World, spec: dict[str, Any]) -> None:
    ends = _road_ends(world, spec)
    if not ends:
        return _skipped(world, spec, f"no two towns match {spec['between']}")
    a, b = ends
    world.add_edge(a, b, Layer.ACCESS, cost=1.0)
    # Agents who reach neighbouring towns can now reach across the new road.
    for home, other in ((a, b), (b, a)):
        for agent_id in world.agents_in_town(home):
            if _reaches_neighbours(world, agent_id):
                world.add_edge(agent_id, other, Layer.ACCESS, cost=1.0)
    message = f"Intervention: a road was built between {world.name(a)} and {world.name(b)}"
    _log(world, spec, (a, b), message)


def _remove_road(world: World, spec: dict[str, Any]) -> None:
    ends = _road_ends(world, spec)
    road = world.get_edge(*ends, Layer.ACCESS) if ends else None
    if road is None:
        return _skipped(world, spec, f"no road between {spec['between']}")
    a, b = ends
    world.remove_edge(road.key)
    for home, other in ((a, b), (b, a)):
        for agent_id in world.agents_in_town(home):
            edge = world.get_edge(agent_id, other, Layer.ACCESS)
            if edge is not None:
                world.remove_edge(edge.key)
    message = f"Intervention: the road between {world.name(a)} and {world.name(b)} was closed"
    _log(world, spec, (a, b), message)


def _add_site(world: World, spec: dict[str, Any]) -> None:
    town = _one(world, spec["town"])
    if town not in world.towns:
        return _skipped(world, spec, f"no town matches {spec['town']!r}")
    if spec["site_kind"] not in world.cfg.site_kinds:
        raise InterventionError(f"add_site.site_kind: no site kind {spec['site_kind']!r}")
    kind = world.cfg.site_kinds[spec["site_kind"]]
    capacity = kind.capacity * spec["scale"]
    name = f"New {spec['site_kind'].title()} ({world.name(town)})"
    site_id = world.new_id("site")
    world.add_site(
        Site(site_id, name, spec["site_kind"], capacity, capacity, kind.regen * spec["scale"])
    )
    world.add_edge(site_id, town, Layer.ACCESS, cost=world.cfg.world.site_access_cost)
    _log(world, spec, (site_id, town), f"Intervention: {name} opened")


def _remove_site(world: World, spec: dict[str, Any]) -> None:
    sites = [t for t in resolve(world, spec["target"]) if t in world.sites]
    if not sites:
        return _skipped(world, spec, f"no site matches {spec['target']!r}")
    for site_id in sites:
        _log(world, spec, (site_id,), f"Intervention: {world.name(site_id)} was closed")
        world.remove_node(site_id)


# --- Social --------------------------------------------------------------------------------------


def _link(world: World, spec: dict[str, Any]) -> None:
    pair = _pair(world, spec)
    if not pair or not all(p in world.agents for p in pair):
        return _skipped(world, spec, f"no two agents match {spec['between']}")
    edge = world.add_edge(*pair, Layer(spec["layer"]))
    edge.strength, edge.trust = float(spec["strength"]), float(spec["trust"])
    edge.last_active = world.tick
    names = " and ".join(world.name(p) for p in pair)
    _log(world, spec, pair, f"Intervention: {names} were given a {spec['layer']} tie")


def _sever(world: World, spec: dict[str, Any]) -> None:
    pair = _pair(world, spec)
    edge = world.get_edge(*pair, Layer(spec["layer"])) if pair else None
    if edge is None:
        return _skipped(world, spec, f"no {spec['layer']} tie between {spec['between']}")
    world.remove_edge(edge.key)
    names = " and ".join(world.name(p) for p in pair)
    _log(world, spec, pair, f"Intervention: the {spec['layer']} tie between {names} was cut")


def _set_trust(world: World, spec: dict[str, Any]) -> None:
    pair = _pair(world, spec)
    tie = world.get_edge(*pair, Layer.SOCIAL) if pair else None
    if tie is None:
        return _skipped(world, spec, f"no social tie between {spec['between']}")
    names = " and ".join(world.name(p) for p in pair)
    message = f"Intervention: trust between {names} set to {spec['value']:g}"
    event_id = _log(world, spec, pair, message)
    before, tie.trust = tie.trust, float(spec["value"])
    world.trust_changes.append(TrustChange(tie.a, tie.b, before, tie.trust, event_id))


def _found_org(world: World, spec: dict[str, Any]) -> None:
    """A new organization with the given members (who leave any organization they were in)."""
    found = [m for target in spec["members"] for m in resolve(world, target)]
    members = list(dict.fromkeys(m for m in found if m in world.agents))
    if not members:
        return _skipped(world, spec, "no members")
    words = world.cfg.organizations.name_words
    founder = world.agents[members[0]]
    name = f"{founder.name}'s {words[len(world.orgs) % len(words)]}"
    org = Org(world.new_id("org"), name, founder.home, world.tick)
    world.add_org(org)
    event_id = _log(world, spec, (org.id, *members), f"Intervention: {org.name} was founded")
    for member in members:
        old = world.org_of(member)
        if old is not None:
            world.remove_edge(world.get_edge(member, old, Layer.MEMBERSHIP).key)
        world.add_edge(member, org.id, Layer.MEMBERSHIP)
        world.log.add(
            world.tick,
            "joined_org",
            (member, org.id),
            f"{world.name(member)} joined {org.name}",
            cause="placed there by an intervention",
            caused_by=(event_id,),
        )


# --- Control -------------------------------------------------------------------------------------


def _reseed(world: World, spec: dict[str, Any]) -> None:
    """A fresh random stream from here on (the same one for the same seed and tick): the world
    is unchanged, only chance differs. Experiments use it to measure how far runs drift apart
    by chance alone."""
    world.rng = random.Random(f"{world.seed}-{world.tick}-reseed")
    _log(world, spec, (), "Intervention: chance was reshuffled (a new random stream)")


APPLY = {
    "remove_agent": _remove_agent,
    "start_drought": _start_drought,
    "end_drought": _end_drought,
    "give": _give,
    "subsidize": _subsidize,
    "set": _set,
    "add_road": _add_road,
    "remove_road": _remove_road,
    "add_site": _add_site,
    "remove_site": _remove_site,
    "link": _link,
    "sever": _sever,
    "set_trust": _set_trust,
    "found_org": _found_org,
    "reseed": _reseed,
}
