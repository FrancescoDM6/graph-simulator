"""Tick phases 1 and 3: eating, starving, leaving, arriving, and deciding what each agent needs."""

from graphsim.model import Agent, Occupation, World
from graphsim.world_gen import create_agent


def consume_food(world: World) -> None:
    cfg = world.cfg
    for agent in list(world.agents.values()):
        agent.food *= 1 - cfg.food_spoil_rate
        if agent.food >= cfg.food_per_tick:
            agent.food -= cfg.food_per_tick
            agent.hunger_ticks = 0
            continue

        agent.food = 0.0
        agent.hunger_ticks += 1
        if agent.hunger_ticks == cfg.starving_notice_after:
            world.log.add(
                world.tick,
                "starving",
                (agent.id,),
                f"{agent.name} is starving",
                cause=f"no food for {agent.hunger_ticks} ticks",
            )
        if agent.hunger_ticks >= cfg.leave_after_hungry:
            _leave(world, agent, cause=f"starved for {agent.hunger_ticks} ticks")


def maybe_add_newcomer(world: World) -> None:
    """A newcomer fills the job a town is most short of, compared with its founding mix."""
    if world.rng.random() >= world.cfg.arrival_chance:
        return
    opening = _biggest_shortfall(world)
    if opening is None:
        return
    town_id, occupation, shortfall = opening
    agent = create_agent(world, occupation, town_id)
    world.log.add(
        world.tick,
        "arrived",
        (agent.id, town_id),
        f"{agent.name} arrived in {world.name(town_id)} as a {occupation}",
        cause=f"{world.name(town_id)} was short of {shortfall} {occupation}(s)",
    )


def evaluate_needs(world: World) -> None:
    for agent in world.agents.values():
        wants = current_wants(world, agent)
        agent.need = wants[0][0] if wants else ""


def current_wants(world: World, agent: Agent) -> list[tuple[str, float]]:
    """What the agent would buy right now, most pressing first: [(good, amount), ...]."""
    cfg = world.cfg
    wants: dict[str, float] = {}  # good -> amount; insertion order = priority
    if agent.food < cfg.food_reserve:
        wants["food"] = cfg.food_buy_target - agent.food
    if agent.occupation == Occupation.FARMER and agent.ore < cfg.ore_reserve:
        wants["ore"] = cfg.ore_buy_target - agent.ore
    return list(wants.items())


def _leave(world: World, agent: Agent, cause: str) -> None:
    world.log.add(
        world.tick,
        "left",
        (agent.id, agent.home),
        f"{agent.name} left {world.name(agent.home)}",
        cause=cause,
    )
    world.remove_node(agent.id)


def _biggest_shortfall(world: World) -> tuple[str, Occupation, int] | None:
    """(town, occupation, how many short) for the most understaffed job, or None if none is."""
    best = None
    for town in world.towns.values():
        for occupation, wanted in town.founding_mix.items():
            present = sum(
                1 for a in world.agents.values() if a.home == town.id and a.occupation == occupation
            )
            shortfall = wanted - present
            if shortfall > 0 and (best is None or shortfall > best[2]):
                best = (town.id, occupation, shortfall)
    return best
