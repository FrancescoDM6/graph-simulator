"""Tick phase 4: agents with needs look for suppliers among the partners they can reach.

Goods and coin move immediately. The social consequences (trust, new ties) are only recorded
here as Interactions; relationships.py applies them in the next phase.
"""

from graphsim.model import Agent, Interaction, Layer, Occupation, World
from graphsim.rules.needs import current_wants

# Who sells each good. Merchants resell both, but only buy from producers.
SUPPLIERS = {
    "food": (Occupation.FARMER, Occupation.MERCHANT),
    "ore": (Occupation.MINER, Occupation.MERCHANT),
}
MIN_AMOUNT = 0.1  # smaller trades than this don't count


def run_trading(world: World) -> None:
    buyers = [a for a in world.agents.values() if a.need]
    world.rng.shuffle(buyers)
    for buyer in buyers:
        # Recomputed per buyer because earlier trades this tick may have changed holdings.
        for good, amount in current_wants(world, buyer):
            _buy(world, buyer, good, amount)


def reachable_partners(world: World, agent_id: str) -> list[str]:
    """Agents in towns this agent can reach, plus its social/trade ties and fellow org members."""
    reachable: dict[str, None] = {}  # insertion-ordered set
    for town_id in world.towns_reachable_by(agent_id):
        for other in world.agents_in_town(town_id):
            reachable[other] = None
    for other in world.neighbors(agent_id, Layer.SOCIAL) + world.neighbors(agent_id, Layer.TRADE):
        reachable[other] = None
    org_id = world.org_of(agent_id)
    if org_id:
        for other in world.members_of(org_id):
            reachable[other] = None
    reachable.pop(agent_id, None)
    return list(reachable)


def spare_amount(world: World, seller: Agent, good: str) -> float:
    """How much of a good the seller is willing to part with."""
    cfg = world.cfg
    if good == "food":
        return seller.food - cfg.food_reserve
    if seller.occupation == Occupation.FARMER:
        return seller.ore - cfg.ore_buy_target  # farmers keep enough ore for their tools
    return seller.ore


def unit_price(world: World, seller: Agent, buyer: Agent, good: str) -> float:
    cfg = world.cfg
    price = cfg.price_food if good == "food" else cfg.price_ore
    if seller.occupation == Occupation.MERCHANT:
        price *= 1 + cfg.merchant_markup
    trust = world.trust(seller.id, buyer.id) or 0.0
    return price * (1 - cfg.trust_discount * trust)


def _buy(world: World, buyer: Agent, good: str, amount: float) -> None:
    suppliers = _suppliers(world, buyer, good)
    for seller_id in _pick_partners(world, buyer.id, suppliers, world.cfg.max_trade_attempts):
        interaction = _attempt_trade(world, buyer, world.agents[seller_id], good, amount)
        world.interactions.append(interaction)
        if interaction.outcome in ("success", "gift"):
            return


def _suppliers(world: World, buyer: Agent, good: str) -> list[str]:
    sellers = SUPPLIERS[good]
    if buyer.occupation == Occupation.MERCHANT:
        sellers = tuple(o for o in sellers if o != Occupation.MERCHANT)
    return [
        other
        for other in reachable_partners(world, buyer.id)
        if world.agents[other].occupation in sellers
    ]


def _pick_partners(world: World, buyer_id: str, candidates: list[str], count: int) -> list[str]:
    """Up to `count` distinct candidates, drawn in proportion to how much the buyer favours them."""
    pool = list(candidates)
    picked: list[str] = []
    while pool and len(picked) < count:
        weights = [_partner_weight(world, buyer_id, c) for c in pool]
        choice = world.rng.choices(pool, weights)[0]
        pool.remove(choice)
        picked.append(choice)
    return picked


def _partner_weight(world: World, buyer_id: str, seller_id: str) -> float:
    trust = world.trust(buyer_id, seller_id)
    weight = world.cfg.stranger_weight if trust is None else trust
    trade_tie = world.get_edge(buyer_id, seller_id, Layer.TRADE)
    if trade_tie:
        weight += trade_tie.strength  # habit: people go back to their regular partners
    return max(weight, 0.01)


def _attempt_trade(
    world: World, buyer: Agent, seller: Agent, good: str, amount: float
) -> Interaction:
    cfg = world.cfg
    spare = spare_amount(world, seller, good)
    if spare < MIN_AMOUNT:
        return _interaction(
            buyer, seller, good, 0.0, "no_surplus",
            f"{buyer.name} wanted {good} but {seller.name} had none to spare",
        )

    price = unit_price(world, seller, buyer, good)
    quantity = min(amount, spare, buyer.coin / price)
    if quantity >= MIN_AMOUNT:
        _transfer(buyer, seller, good, quantity, coin=quantity * price)
        return _interaction(
            buyer, seller, good, quantity, "success",
            f"{buyer.name} bought {quantity:.1f} {good} from {seller.name} at {price:.2f} each",
        )

    tie = world.get_edge(buyer.id, seller.id, Layer.SOCIAL)
    is_close_friend = tie is not None and tie.strength >= cfg.gift_min_strength
    if good == "food" and buyer.food < cfg.food_per_tick and is_close_friend:
        gift = min(cfg.gift_amount, spare)
        _transfer(buyer, seller, good, gift, coin=0.0)
        return _interaction(
            buyer, seller, good, gift, "gift",
            f"{buyer.name} was hungry and broke; {seller.name} is a close friend",
        )

    return _interaction(
        buyer, seller, good, 0.0, "cannot_afford",
        f"{buyer.name} couldn't afford {good} at {price:.2f} (has {buyer.coin:.1f} coin)",
    )


def _transfer(buyer: Agent, seller: Agent, good: str, quantity: float, coin: float) -> None:
    if good == "food":
        seller.food -= quantity
        buyer.food += quantity
    else:
        seller.ore -= quantity
        buyer.ore += quantity
    buyer.coin -= coin
    seller.coin += coin


def _interaction(
    buyer: Agent, seller: Agent, good: str, amount: float, outcome: str, cause: str
) -> Interaction:
    return Interaction(buyer.id, seller.id, good, amount, outcome, cause)
