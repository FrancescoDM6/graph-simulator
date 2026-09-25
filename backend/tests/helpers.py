"""Tiny hand-built worlds for testing one rule at a time."""

from dataclasses import replace

from graphsim.config import SimConfig
from graphsim.model import Agent, Layer, Occupation, Town, World
from graphsim.world_gen import create_agent, empty_world

TOWN = "town-001"


def make_world(**config_overrides) -> World:
    """A world with a single town and no agents. Override config fields by keyword."""
    world = empty_world(replace(SimConfig(), **config_overrides), seed=0)
    add_town(world, "Testville")  # gets the id TOWN
    return world


def add_town(world: World, name: str, road_to: str | None = None) -> str:
    town_id = world.new_id("town")
    world.add_town(Town(town_id, name, founding_mix={}))
    if road_to:
        world.add_edge(town_id, road_to, Layer.ACCESS)
    return town_id


def add_agent(
    world: World,
    occupation: Occupation,
    *,
    food: float = 8.0,
    ore: float = 0.0,
    coin: float = 10.0,
    home: str = TOWN,
) -> Agent:
    agent = create_agent(world, occupation, home)
    agent.food, agent.ore, agent.coin = food, ore, coin
    return agent


def befriend(world: World, a: Agent, b: Agent, strength: float, trust: float) -> None:
    world.add_edge(a.id, b.id, Layer.SOCIAL, strength=strength, trust=trust)
