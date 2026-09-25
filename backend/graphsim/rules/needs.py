"""Tick phases 1 and 3: eating, starving, leaving, arriving, and deciding what each agent needs."""

from statistics import mean

from graphsim.model import Agent, Occupation, World
from graphsim.world_gen import create_agent, towns_for_occupation


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
    """A newcomer is drawn to the richest town and takes up its best-paid occupation."""
    cfg = world.cfg
    if len(world.agents) >= cfg.max_population or world.rng.random() >= cfg.arrival_chance:
        return

    town_id, town_wealth = _richest_town(world)
    occupation = _best_paid_occupation(world, town_id)
    agent = create_agent(world, occupation, town_id, cfg.start_food, cfg.start_ore, cfg.start_coin)
    world.log.add(
        world.tick,
        "arrived",
        (agent.id, town_id),
        f"{agent.name} arrived in {world.name(town_id)} as a {occupation}",
        cause=f"{world.name(town_id)} is the richest town (avg {town_wealth:.1f} coin)",
    )


def evaluate_needs(world: World) -> None:
    for agent in world.agents.values():
        wants = current_wants(world, agent)
        if agent.food < world.cfg.food_reserve:
            agent.need = "food"
        elif not wants:
            agent.need = ""
        elif agent.occupation == Occupation.MERCHANT:
            agent.need = "stock"
        else:
            agent.need = wants[0][0]


def current_wants(world: World, agent: Agent) -> list[tuple[str, float]]:
    """What the agent would buy right now, most pressing first: [(good, amount), ...]."""
    cfg = world.cfg
    wants: list[tuple[str, float]] = []
    if agent.food < cfg.food_reserve:
        wants.append(("food", cfg.food_buy_target - agent.food))
    if agent.occupation == Occupation.FARMER and agent.ore < cfg.ore_reserve:
        wants.append(("ore", cfg.ore_buy_target - agent.ore))
    if agent.occupation == Occupation.MERCHANT:
        # Merchants restock for resale on top of their own food needs.
        stock_food = agent.food - cfg.food_reserve
        if stock_food < cfg.merchant_stock_target and not wants:
            wants.append(("food", cfg.merchant_stock_target - max(stock_food, 0.0)))
        if agent.ore < cfg.merchant_stock_target:
            wants.append(("ore", cfg.merchant_stock_target - agent.ore))
    return wants


def _leave(world: World, agent: Agent, cause: str) -> None:
    world.log.add(
        world.tick,
        "left",
        (agent.id, agent.home),
        f"{agent.name} left {world.name(agent.home)}",
        cause=cause,
    )
    world.remove_node(agent.id)


def _richest_town(world: World) -> tuple[str, float]:
    best_town, best_wealth = "", -1.0
    for town_id in world.towns:
        residents = [world.agents[a] for a in world.agents_in_town(town_id)]
        wealth = mean(a.coin for a in residents) if residents else 0.0
        if wealth > best_wealth:
            best_town, best_wealth = town_id, wealth
    return best_town, best_wealth


def _best_paid_occupation(world: World, town_id: str) -> Occupation:
    """The occupation (that can work in this town) whose members hold the most coin on average.

    An occupation nobody practises yet counts as very attractive, so empty niches get filled.
    """
    best, best_wealth = Occupation.MERCHANT, -1.0
    for occupation in Occupation:
        if town_id not in towns_for_occupation(world, occupation):
            continue
        coins = [a.coin for a in world.agents.values() if a.occupation == occupation]
        wealth = mean(coins) if coins else float("inf")
        if wealth > best_wealth:
            best, best_wealth = occupation, wealth
    return best
