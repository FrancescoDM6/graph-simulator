"""Builds the starting world from a config and a seed. See the geography in docs/spec.md."""

import random

from graphsim.config import SimConfig
from graphsim.model import Agent, Layer, Occupation, Site, SiteKind, Town, World

FIRST_NAMES = [
    "Ada", "Alma", "Anselm", "Ansel", "Aurel", "Basil", "Bea", "Bram", "Brin", "Cass",
    "Cato", "Cora", "Corin", "Dara", "Dell", "Dov", "Edda", "Edric", "Elka", "Emil",
    "Enna", "Ezra", "Fen", "Finn", "Frida", "Gale", "Gil", "Greta", "Hale", "Hana",
    "Hugo", "Ida", "Ilse", "Ines", "Ivo", "Jana", "Joss", "Jura", "Kai", "Kira",
    "Lars", "Lena", "Lio", "Lorn", "Mae", "Mara", "Milo", "Mira", "Nell", "Nils",
    "Noor", "Odo", "Olan", "Opal", "Orla", "Otto", "Pell", "Pia", "Quill", "Rafe",
    "Rhea", "Rolf", "Rosa", "Rune", "Saga", "Sela", "Sven", "Tam", "Tess", "Theo",
    "Tova", "Ulla", "Una", "Vale", "Vera", "Wren", "Yara", "Yves", "Zane", "Zora",
]  # fmt: skip

FARMER, MINER, MERCHANT = Occupation.FARMER, Occupation.MINER, Occupation.MERCHANT
FARM, MINE = SiteKind.FARM, SiteKind.MINE

# Towns in road order (each has a road to the next): name, sites, founding population.
# Newcomers later fill whichever occupation a town is most short of, relative to this mix.
TOWNS = [
    ("Ashford", [("North Farm", FARM)],
        {FARMER: 12, MERCHANT: 1}),
    ("Millbrook", [("South Farm", FARM), ("Copper Mine", MINE)],
        {FARMER: 9, MINER: 3, MERCHANT: 2}),
    ("Stonehold", [("Iron Mine", MINE)],
        {MINER: 5, MERCHANT: 1}),
]  # fmt: skip


def build_world(cfg: SimConfig, seed: int) -> World:
    world = empty_world(cfg, seed)

    previous_town_id = None
    for town_name, sites, founding_mix in TOWNS:
        town = Town(world.new_id("town"), town_name, founding_mix)
        world.add_town(town)
        if previous_town_id:
            world.add_edge(previous_town_id, town.id, Layer.ACCESS, cost=1.0)
        previous_town_id = town.id
        for site_name, kind in sites:
            site = _make_site(world, site_name, kind)
            world.add_site(site)
            world.add_edge(site.id, town.id, Layer.ACCESS, cost=0.5)

    for town in world.towns.values():
        for occupation, count in town.founding_mix.items():
            for _ in range(count):
                create_agent(world, occupation, town.id)

    _add_initial_acquaintances(world)
    return world


def empty_world(cfg: SimConfig, seed: int) -> World:
    """A world with no nodes yet, but with its random generator and starting prices."""
    world = World(cfg=cfg, seed=seed, rng=random.Random(seed))
    world.prices = {"food": cfg.start_price_food, "ore": cfg.start_price_ore}
    world.logged_prices = dict(world.prices)
    return world


def create_agent(world: World, occupation: Occupation, home: str) -> Agent:
    """Adds an agent plus its access edges. Merchants can also reach neighbouring towns."""
    cfg = world.cfg
    agent = Agent(
        id=world.new_id("agent"),
        name=_unused_name(world),
        occupation=occupation,
        home=home,
        food=cfg.start_food,
        ore=cfg.start_ore,
        coin=cfg.start_coin,
        arrived=world.tick,
    )
    world.add_agent(agent)
    world.add_edge(agent.id, home, Layer.ACCESS, cost=0.0)
    if occupation == Occupation.MERCHANT:
        for town_id in world.neighbors(home, Layer.ACCESS):
            if town_id in world.towns:
                world.add_edge(agent.id, town_id, Layer.ACCESS, cost=1.0)
    return agent


def _make_site(world: World, name: str, kind: SiteKind) -> Site:
    cfg = world.cfg
    if kind == SiteKind.FARM:
        capacity, regen = cfg.farm_capacity, cfg.farm_regen
    else:
        capacity, regen = cfg.mine_capacity, cfg.mine_regen
    return Site(world.new_id("site"), name, kind, stock=capacity, capacity=capacity, regen=regen)


def _add_initial_acquaintances(world: World) -> None:
    cfg = world.cfg
    for agent in list(world.agents.values()):
        townsfolk = [a for a in world.agents_in_town(agent.home) if a != agent.id]
        for other in world.rng.sample(townsfolk, min(cfg.initial_ties_per_agent, len(townsfolk))):
            world.add_edge(
                agent.id, other, Layer.SOCIAL, strength=cfg.meet_strength, trust=cfg.initial_trust
            )


def _unused_name(world: World) -> str:
    free = [n for n in FIRST_NAMES if n not in world.used_names]
    if free:
        name = world.rng.choice(free)
    else:
        # Every name has been used: add a numeral, e.g. "Ada II".
        base = world.rng.choice(FIRST_NAMES)
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
