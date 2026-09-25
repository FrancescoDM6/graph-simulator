"""Tick phase 4: agents with needs look for producers they can reach, directly or via a merchant.

A buyer can deal directly with producers it can meet (same town, social/trade ties, fellow org
members). It can also reach further through any merchant it can meet: the merchant brokers
the deal with a producer the merchant can meet, and takes a commission. Goods go straight
from producer to buyer; merchants never hold stock.

Goods and coin move immediately. The social consequences (trust, trade ties) are only
recorded here as Interactions; relationships.py applies them in the next phase.
"""

from dataclasses import dataclass

from graphsim.model import Agent, Interaction, Layer, Occupation, World
from graphsim.rules.needs import current_wants

PRODUCERS = {"food": Occupation.FARMER, "ore": Occupation.MINER}
MIN_AMOUNT = 0.1  # smaller trades than this don't count


@dataclass(frozen=True)
class Offer:
    seller: str
    broker: str | None = None  # merchant connecting buyer and seller, if they can't meet directly

    def contact(self) -> str:
        """The person the buyer actually deals with."""
        return self.broker or self.seller


def run_trading(world: World) -> None:
    buyers = [a for a in world.agents.values() if a.need]
    world.rng.shuffle(buyers)
    for buyer in buyers:
        # Recomputed per buyer because earlier trades this tick may have changed holdings.
        for good, amount in current_wants(world, buyer):
            _buy(world, buyer, good, amount)


def reachable_partners(world: World, agent_id: str) -> list[str]:
    """Everyone the agent can meet: people present in any town it can reach (residents and
    visiting merchants), plus its social/trade ties and fellow org members."""
    reachable: dict[str, None] = {}  # insertion-ordered set
    for town_id in world.towns_reachable_by(agent_id):
        for other in world.agents_present_in(town_id):
            reachable[other] = None
    for other in world.neighbors(agent_id, Layer.SOCIAL) + world.neighbors(agent_id, Layer.TRADE):
        reachable[other] = None
    org_id = world.org_of(agent_id)
    if org_id:
        for other in world.members_of(org_id):
            reachable[other] = None
    reachable.pop(agent_id, None)
    return list(reachable)


def available_offers(world: World, buyer: Agent, good: str) -> list[Offer]:
    """Producers the buyer can reach directly, then those it can only reach through a merchant."""
    producer = PRODUCERS[good]
    partners = reachable_partners(world, buyer.id)
    offers: dict[str, Offer] = {}  # seller -> offer; a direct offer beats a brokered one
    for other in partners:
        if world.agents[other].occupation == producer:
            offers[other] = Offer(other)
    for merchant in partners:
        if world.agents[merchant].occupation != Occupation.MERCHANT:
            continue
        for other in reachable_partners(world, merchant):
            if other != buyer.id and other not in offers:
                if world.agents[other].occupation == producer:
                    offers[other] = Offer(other, broker=merchant)
    return list(offers.values())


def spare_amount(world: World, seller: Agent, good: str) -> float:
    """How much of a good the seller is willing to part with."""
    if good == "food":
        return seller.food - world.cfg.food_reserve
    return seller.ore


def unit_price(world: World, offer: Offer, buyer: Agent, good: str) -> tuple[float, float]:
    """(what the buyer pays per unit, the part of that which is the broker's commission).

    Trusted contacts give a discount; brokered deals add the merchant's markup.
    """
    cfg = world.cfg
    trust = world.trust(buyer.id, offer.contact()) or 0.0
    price = world.prices[good] * (1 - cfg.trust_discount * trust)
    commission = price * cfg.merchant_markup if offer.broker else 0.0
    return price + commission, commission


def _buy(world: World, buyer: Agent, good: str, amount: float) -> None:
    offers = available_offers(world, buyer, good)
    for offer in _pick_offers(world, buyer.id, offers, world.cfg.max_trade_attempts):
        interaction = _attempt_trade(world, buyer, offer, good, amount)
        world.interactions.append(interaction)
        if interaction.outcome in ("success", "gift"):
            return


def _pick_offers(world: World, buyer_id: str, offers: list[Offer], count: int) -> list[Offer]:
    """Up to `count` distinct offers, drawn in proportion to how much the buyer favours them."""
    pool = list(offers)
    picked: list[Offer] = []
    while pool and len(picked) < count:
        weights = [_offer_weight(world, buyer_id, o) for o in pool]
        choice = world.rng.choices(pool, weights)[0]
        pool.remove(choice)
        picked.append(choice)
    return picked


def _offer_weight(world: World, buyer_id: str, offer: Offer) -> float:
    cfg = world.cfg
    contact = offer.contact()
    trust = world.trust(buyer_id, contact)
    weight = cfg.stranger_weight if trust is None else trust
    trade_tie = world.get_edge(buyer_id, contact, Layer.TRADE)
    if trade_tie:
        weight += trade_tie.strength  # habit: people go back to their regular partners
    if offer.broker:
        weight *= cfg.brokered_weight  # a middleman is the second choice
    return max(weight, 0.01)


def _attempt_trade(
    world: World, buyer: Agent, offer: Offer, good: str, amount: float
) -> Interaction:
    seller = world.agents[offer.seller]
    via = f" via {world.name(offer.broker)}" if offer.broker else ""

    spare = spare_amount(world, seller, good)
    price, commission = unit_price(world, offer, buyer, good)
    quantity = min(amount, spare, buyer.coin / price)
    if quantity >= MIN_AMOUNT:
        _move_goods(seller, buyer, good, quantity)
        buyer.coin -= quantity * price
        seller.coin += quantity * (price - commission)
        if offer.broker:
            world.agents[offer.broker].coin += quantity * commission
        cause = f"{buyer.name} bought {quantity:.1f} {good} from {seller.name}{via} at {price:.2f}"
        return _interaction(buyer, offer, good, quantity, "success", cause)

    plea = _ask_for_help(world, buyer, offer, good)
    if plea is not None:
        return plea
    if spare < MIN_AMOUNT:
        cause = f"{buyer.name} wanted {good}{via} but {seller.name} had none to spare"
        return _interaction(buyer, offer, good, 0.0, "no_surplus", cause)
    cause = f"{buyer.name} couldn't afford {good}{via} at {price:.2f} (has {buyer.coin:.1f} coin)"
    return _interaction(buyer, offer, good, 0.0, "cannot_afford", cause)


def _ask_for_help(world: World, buyer: Agent, offer: Offer, good: str) -> Interaction | None:
    """A hungry buyer who couldn't trade asks the seller for food, if they know each other.

    If the seller could give some without going hungry, a close friend gives it; anyone
    else refuses, and that refusal costs trust. Returns None when there was nothing to ask.
    """
    cfg = world.cfg
    seller = world.agents[offer.seller]
    tie = world.get_edge(buyer.id, seller.id, Layer.SOCIAL)
    if good != "food" or buyer.food >= cfg.food_per_tick or tie is None or offer.broker:
        return None
    could_give = seller.food - 2 * cfg.food_per_tick  # what they can spare without going hungry
    if could_give < MIN_AMOUNT:
        return None
    if tie.strength >= cfg.gift_min_strength:
        gift = min(cfg.gift_amount, could_give)
        _move_goods(seller, buyer, good, gift)
        cause = f"{buyer.name} was starving; {seller.name} is a close friend"
        return _interaction(buyer, offer, good, gift, "gift", cause)
    cause = f"{buyer.name} was starving; {seller.name} had {seller.food:.0f} food but kept it"
    return _interaction(buyer, offer, good, 0.0, "refused", cause)


def _move_goods(seller: Agent, buyer: Agent, good: str, quantity: float) -> None:
    if good == "food":
        seller.food -= quantity
        buyer.food += quantity
    else:
        seller.ore -= quantity
        buyer.ore += quantity


def _interaction(
    buyer: Agent, offer: Offer, good: str, amount: float, outcome: str, cause: str
) -> Interaction:
    return Interaction(buyer.id, offer.seller, good, amount, outcome, cause, broker=offer.broker)
