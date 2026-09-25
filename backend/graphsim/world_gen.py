"""Builds the starting world from a SimConfig and a seed (geography: scenario.toml [world])."""

import random

from graphsim.config import SimConfig
from graphsim.model import Agent, Layer, Site, Town, World


def build_world(cfg: SimConfig, seed: int) -> World:
    world = empty_world(cfg, seed)

    town_ids: dict[str, str] = {}  # town name -> id
    for town_name, spec in cfg.world.towns.items():
        town = Town(world.new_id("town"), town_name, founding_mix(cfg, town_name))
        world.add_town(town)
        town_ids[town_name] = town.id
        # Roads are added as soon as both of their towns exist.
        for road in cfg.world.roads:
            if town_name in (road.from_, road.to) and {road.from_, road.to} <= town_ids.keys():
                world.add_edge(
                    town_ids[road.from_], town_ids[road.to], Layer.ACCESS, cost=road.cost
                )
        for site_spec in spec.sites:
            kind = cfg.site_kinds[site_spec.kind]
            site = Site(
                world.new_id("site"),
                site_spec.name,
                site_spec.kind,
                stock=kind.capacity,
                capacity=kind.capacity,
                regen=kind.regen,
            )
            world.add_site(site)
            world.add_edge(site.id, town.id, Layer.ACCESS, cost=cfg.world.site_access_cost)

    for town in world.towns.values():
        for occupation, count in town.founding_mix.items():
            for _ in range(count):
                create_agent(world, occupation, town.id)

    _add_initial_acquaintances(world)
    return world


def empty_world(cfg: SimConfig, seed: int) -> World:
    """A world with no nodes yet, but with its random generator and starting prices."""
    world = World(cfg=cfg, seed=seed, rng=random.Random(seed))
    world.prices = {good: spec.start_price for good, spec in cfg.goods.items()}
    world.logged_prices = dict(world.prices)
    return world


def founding_mix(cfg: SimConfig, town_name: str) -> dict[str, int]:
    """The town's founding population. Without brokering, broker occupations don't exist."""
    return {
        occupation: count
        for occupation, count in cfg.world.towns[town_name].founding.items()
        if not cfg.occupations[occupation].brokers or cfg.mechanisms.brokering
    }


def create_agent(world: World, occupation: str, home: str) -> Agent:
    """Adds an agent plus its access edges (home town, and neighbouring towns if its reach
    allows)."""
    cfg = world.cfg
    agent = Agent(
        id=world.new_id("agent"),
        name=_unused_name(world),
        occupation=occupation,
        home=home,
        inventory={good: spec.start_amount for good, spec in cfg.goods.items()},
        coin=cfg.population.start_coin,
        arrived=world.tick,
    )
    world.add_agent(agent)
    world.record_flow(agent.id, "coin", agent.coin, "endowment")
    for good, amount in agent.inventory.items():
        world.record_flow(agent.id, good, amount, "endowment")
    world.add_edge(agent.id, home, Layer.ACCESS, cost=0.0)
    if cfg.occupations[occupation].reach == "home_and_neighbours":
        for road in world.edges_of(home, Layer.ACCESS):
            town_id = road.other(home)
            if town_id in world.towns:
                world.add_edge(agent.id, town_id, Layer.ACCESS, cost=road.cost)
    return agent


def _add_initial_acquaintances(world: World) -> None:
    rel = world.cfg.relationships
    per_agent = world.cfg.population.initial_ties_per_agent
    for agent in list(world.agents.values()):
        townsfolk = [a for a in world.agents_in_town(agent.home) if a != agent.id]
        for other in world.rng.sample(townsfolk, min(per_agent, len(townsfolk))):
            world.add_edge(
                agent.id, other, Layer.SOCIAL, strength=rel.meet_strength, trust=rel.initial_trust
            )


def _unused_name(world: World) -> str:
    names = world.cfg.world.names
    free = [n for n in names if n not in world.used_names]
    if free:
        name = world.rng.choice(free)
    else:
        # Every name has been used: add a numeral, e.g. "Ada II".
        base = world.rng.choice(names)
        numeral = 2
        while f"{base} {_roman(numeral)}" in world.used_names:
            numeral += 1
        name = f"{base} {_roman(numeral)}"
    world.used_names.add(name)
    return name


def _roman(n: int) -> str:
    numerals = [(10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]
    out = ""
    for value, letters in numerals:
        while n >= value:
            out += letters
            n -= value
    return out
