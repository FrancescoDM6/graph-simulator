"""Tick phases 1 and 3: eating, starving, leaving, arriving, and deciding what each agent needs."""

from graphsim.events import FAILED_PURCHASE_KINDS, ids
from graphsim.model import Agent, World
from graphsim.world_gen import create_agent


def consume(world: World) -> None:
    """Held goods spoil, then agents eat every good that is eaten. Anyone who is short of an
    eaten good goes hungry; hungry for too long, they leave."""
    cfg = world.cfg
    for agent in list(world.agents.values()):
        short_of = ""
        for good, spec in cfg.goods.items():
            held = agent.inventory[good]
            agent.inventory[good] *= 1 - spec.spoil_rate
            world.record_flow(agent.id, good, agent.inventory[good] - held, "spoiled")
            if spec.eaten_per_tick <= 0:
                continue
            held = agent.inventory[good]
            if held >= spec.eaten_per_tick:
                agent.inventory[good] -= spec.eaten_per_tick
            else:
                agent.inventory[good] = 0.0
                short_of = short_of or good
            world.record_flow(agent.id, good, agent.inventory[good] - held, "eaten")
        if not short_of:
            agent.hunger_ticks = 0
            continue

        agent.hunger_ticks += 1
        if agent.hunger_ticks == cfg.population.starving_notice_after:
            # Why: the agent's own purchases that failed during this hungry spell, and any
            # drought. (Its failures as a buyer only: the buyer is always the first subject.)
            episode_start = world.tick - agent.hunger_ticks
            failures = [
                e
                for e in world.log.recent(
                    agent.id, FAILED_PURCHASE_KINDS, since_tick=episode_start, limit=50
                )
                if e.subjects[0] == agent.id
            ][:3]
            world.log.add(
                world.tick,
                "starving",
                (agent.id,),
                f"{agent.name} is starving",
                cause=f"no {short_of} for {agent.hunger_ticks} ticks",
                caused_by=ids(failures) + drought_cause(world, short_of),
            )
        if agent.hunger_ticks >= cfg.population.leave_after_hungry:
            starving = world.log.latest(agent.id, ("starving",))
            _leave(world, agent, f"starved for {agent.hunger_ticks} ticks", ids([starving]))


def maybe_add_newcomer(world: World) -> None:
    """A newcomer fills the job a town is most short of, compared with its founding mix."""
    if world.rng.random() >= world.cfg.population.arrival_chance:
        return
    opening = _biggest_shortfall(world)
    if opening is None:
        return
    town_id, occupation, shortfall = opening
    agent = create_agent(world, occupation, town_id)
    last_departure = world.log.latest(town_id, ("left",))
    world.log.add(
        world.tick,
        "arrived",
        (agent.id, town_id),
        f"{agent.name} arrived in {world.name(town_id)} as a {occupation}",
        cause=f"{world.name(town_id)} was short of {shortfall} {occupation}(s)",
        caused_by=ids([last_departure]),
    )


def evaluate_needs(world: World) -> None:
    for agent in world.agents.values():
        wants = current_wants(world, agent)
        agent.need = wants[0][0] if wants else ""


def current_wants(world: World, agent: Agent) -> list[tuple[str, float]]:
    """What the agent would buy right now, in the order goods are listed in the scenario:
    every good it eats or uses as a tool, whenever its holding is below that good's reserve."""
    cfg = world.cfg
    wants: list[tuple[str, float]] = []
    for good, spec in cfg.goods.items():
        held = agent.inventory[good]
        if cfg.needs_good(agent.occupation, good) and held < spec.reserve:
            wants.append((good, spec.buy_target - held))
    return wants


def starving_cause(world: World, agent: Agent) -> tuple[int, ...]:
    """The agent's current "starving" event, if it is in the middle of a hungry spell."""
    if agent.hunger_ticks < world.cfg.population.starving_notice_after:
        return ()
    since = world.tick - agent.hunger_ticks
    return ids([world.log.latest(agent.id, ("starving",), since_tick=since)])


def drought_cause(world: World, good: str) -> tuple[int, ...]:
    """The current drought, if it affects the supply of this good."""
    if world.drought_event is None:
        return ()
    affected = any(
        kind.produces == good and kind.drought_sensitive for kind in world.cfg.site_kinds.values()
    )
    return (world.drought_event,) if affected else ()


def _leave(world: World, agent: Agent, cause: str, caused_by: tuple[int, ...]) -> None:
    world.record_flow(agent.id, "coin", -agent.coin, "departure")
    for good, held in agent.inventory.items():
        world.record_flow(agent.id, good, -held, "departure")
    world.log.add(
        world.tick,
        "left",
        (agent.id, agent.home),
        f"{agent.name} left {world.name(agent.home)}",
        cause=cause,
        caused_by=caused_by,
    )
    world.remove_node(agent.id)


def _biggest_shortfall(world: World) -> tuple[str, str, int] | None:
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
