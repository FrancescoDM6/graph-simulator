"""Tick phase 4 (end): prices react to how this tick's trades went, and towns share wealth.

There is one base price per good. If buyers keep finding sellers with nothing to spare, the
price rises; if buyers keep being unable to pay, it falls.

Each town also takes a small levy from its residents' coin and splits it equally among them.
Without it, coin piles up with whoever earns more than they spend (usually a dominant broker),
everyone else goes broke, and trade stops.
"""

from graphsim.model import World
from graphsim.rules.needs import drought_cause


def update_prices(world: World) -> None:
    if not world.cfg.mechanisms.price_adjustment:
        return
    prices = world.cfg.prices
    for good in world.cfg.goods:
        attempts = [i for i in world.interactions if i.good == good]
        if not attempts:
            continue
        shortages = sum(i.outcome == "no_surplus" for i in attempts)
        unaffordable = sum(i.outcome in ("cannot_afford", "refused") for i in attempts)
        pressure = (shortages - unaffordable) / len(attempts)  # -1 (too dear) .. +1 (too scarce)
        price = world.prices[good] * (1 + prices.adjust_rate * pressure)
        world.prices[good] = min(prices.max, max(prices.min, price))
        _log_big_moves(world, good, shortages, unaffordable, len(attempts))


def share_town_levy(world: World) -> None:
    if not world.cfg.mechanisms.town_levy:
        return
    for town_id in world.towns:
        residents = [world.agents[a] for a in world.agents_in_town(town_id)]
        if not residents:
            continue
        pot = 0.0
        for agent in residents:
            levy = agent.coin * world.cfg.prices.town_levy
            agent.coin -= levy
            pot += levy
        for agent in residents:
            agent.coin += pot / len(residents)


def _log_big_moves(
    world: World, good: str, shortages: int, unaffordable: int, attempts: int
) -> None:
    price, last_logged = world.prices[good], world.logged_prices[good]
    if abs(price / last_logged - 1) < world.cfg.prices.event_change:
        return
    world.logged_prices[good] = price
    direction = "rose" if price > last_logged else "fell"
    # Point at a few of the attempts that pushed the price this way.
    pushing = ("no_surplus",) if direction == "rose" else ("cannot_afford", "refused")
    examples = [i.event_id for i in world.interactions if i.good == good and i.outcome in pushing]
    world.log.add(
        world.tick,
        f"price_{direction}",
        (),
        f"The price of {good} {direction} to {price:.2f}",
        cause=f"of {attempts} attempts to buy {good} this tick, {shortages} found nothing "
        f"to spare and {unaffordable} couldn't pay",
        caused_by=drought_cause(world, good) + tuple(examples[:5]),
    )
