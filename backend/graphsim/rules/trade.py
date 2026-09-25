"""Tick phase 4: agents with needs look for producers they can reach, directly or via a broker.

A buyer can deal directly with producers it can meet (same town, social/trade ties, fellow org
members). It can also reach further through any broker it can meet (an occupation with
`brokers = true`): the broker connects the buyer with a producer the broker can meet, and takes
a commission. Goods go straight from producer to buyer; brokers never hold stock.

`mechanisms.partner_choice` can replace this network routing with random partners (ablations).

Goods and coin move immediately. The social consequences (trust, trade ties) are only
recorded here as Interactions; relationships.py applies them in the next phase.
"""

from dataclasses import dataclass

from graphsim.model import Agent, Interaction, Layer, World
from graphsim.rules.needs import current_wants, drought_cause, starving_cause

# The event kind logged for each interaction outcome. Gifts and refusals are notable;
# ordinary trade attempts are detail events (see events.py).
EVENT_KINDS = {
    "success": "trade",
    "gift": "gift",
    "refused": "refused",
    "no_surplus": "no_surplus",
    "cannot_afford": "cannot_afford",
}


@dataclass(frozen=True)
class Offer:
    seller: str
    broker: str | None = None  # broker connecting buyer and seller, if they can't meet directly

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
    visiting brokers), plus its social/trade ties and fellow org members."""
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
    """Producers the buyer can reach directly, then those it can only reach through a broker."""
    cfg = world.cfg
    producers = cfg.producers_of(good)
    if cfg.mechanisms.partner_choice == "random_global":
        # Ablation: the network plays no part; any producer anywhere is a candidate.
        return [
            Offer(a.id)
            for a in world.agents.values()
            if a.occupation in producers and a.id != buyer.id
        ]

    partners = reachable_partners(world, buyer.id)
    offers: dict[str, Offer] = {}  # seller -> offer; a direct offer beats a brokered one
    for other in partners:
        if world.agents[other].occupation in producers:
            offers[other] = Offer(other)
    for broker in partners:
        if not cfg.is_broker(world.agents[broker].occupation):
            continue
        for other in reachable_partners(world, broker):
            if other != buyer.id and other not in offers:
                if world.agents[other].occupation in producers:
                    offers[other] = Offer(other, broker=broker)
    return list(offers.values())


def spare_amount(world: World, seller: Agent, good: str) -> float:
    """How much of a good the seller is willing to part with: everything above the reserve it
    keeps for itself (if it eats the good or uses it as a tool)."""
    held = seller.inventory[good]
    if world.cfg.needs_good(seller.occupation, good):
        return held - world.cfg.goods[good].reserve
    return held


def unit_price(world: World, offer: Offer, buyer: Agent, good: str) -> tuple[float, float]:
    """(what the buyer pays per unit, the part of that which is the broker's commission).

    Trusted contacts give a discount; brokered deals add the broker's commission.
    """
    trade = world.cfg.trade
    trust = world.trust(buyer.id, offer.contact()) or 0.0
    price = world.prices[good] * (1 - trade.trust_discount * trust)
    commission = price * trade.broker_commission if offer.broker else 0.0
    return price + commission, commission


def _buy(world: World, buyer: Agent, good: str, amount: float) -> None:
    reserve = world.cfg.goods[good].reserve
    why = f"{buyer.name} had {buyer.inventory[good]:.1f} {good}, wanted at least {reserve:g}"
    context = starving_cause(world, buyer) + drought_cause(world, good)
    offers = available_offers(world, buyer, good)
    if not offers:
        world.log.add(
            world.tick,
            "no_offers",
            (buyer.id,),
            f"{buyer.name} found nobody selling {good}",
            cause=why,
            caused_by=context,
            detail=True,
        )
        return
    for offer in _pick_offers(world, buyer.id, offers, world.cfg.trade.max_attempts):
        interaction = _attempt_trade(world, buyer, offer, good, amount)
        _log_interaction(world, interaction, why, context)
        world.interactions.append(interaction)
        if interaction.outcome in ("success", "gift"):
            return


def _log_interaction(
    world: World, interaction: Interaction, why: str, context: tuple[int, ...]
) -> None:
    buyer, seller = world.name(interaction.buyer), world.name(interaction.seller)
    subjects = (interaction.buyer, interaction.seller)
    if interaction.broker:
        subjects += (interaction.broker,)
    if interaction.outcome == "gift":
        subjects = (interaction.seller, interaction.buyer)
        message = f"{seller} gave {interaction.amount:.1f} {interaction.good} to {buyer}"
        cause = interaction.cause
    elif interaction.outcome == "refused":
        message, cause = f"{seller} refused to help {buyer}", interaction.cause
    else:
        message, cause = interaction.cause, why
    event = world.log.add(
        world.tick,
        EVENT_KINDS[interaction.outcome],
        subjects,
        message,
        cause=cause,
        caused_by=context,
        detail=interaction.outcome not in ("gift", "refused"),
    )
    interaction.event_id = event.id


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
    trade = world.cfg.trade
    if world.cfg.mechanisms.partner_choice != "network":
        return 1.0  # ablation: no preference for trusted or habitual partners
    contact = offer.contact()
    trust = world.trust(buyer_id, contact)
    weight = trade.stranger_weight if trust is None else trust
    trade_tie = world.get_edge(buyer_id, contact, Layer.TRADE)
    if trade_tie:
        weight += trade_tie.strength  # habit: people go back to their regular partners
    if offer.broker:
        weight *= trade.brokered_weight  # a middleman is the second choice
    return max(weight, 0.01)


def _attempt_trade(
    world: World, buyer: Agent, offer: Offer, good: str, amount: float
) -> Interaction:
    seller = world.agents[offer.seller]
    via = f" via {world.name(offer.broker)}" if offer.broker else ""
    min_amount = world.cfg.trade.min_amount

    spare = spare_amount(world, seller, good)
    price, commission = unit_price(world, offer, buyer, good)
    quantity = min(amount, spare, buyer.coin / price)
    if quantity >= min_amount:
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
    if spare < min_amount:
        cause = f"{buyer.name} wanted {good}{via} but {seller.name} had none to spare"
        return _interaction(buyer, offer, good, 0.0, "no_surplus", cause)
    cause = f"{buyer.name} couldn't afford {good}{via} at {price:.2f} (has {buyer.coin:.1f} coin)"
    return _interaction(buyer, offer, good, 0.0, "cannot_afford", cause)


def _ask_for_help(world: World, buyer: Agent, offer: Offer, good: str) -> Interaction | None:
    """A starving buyer who couldn't trade asks the seller for help, if they know each other.

    If the seller could give some without going hungry, a close friend gives it; anyone
    else refuses, and that refusal costs trust. Returns None when there was nothing to ask.
    With `mechanisms.gifting` off, nobody asks: no gifts and no refusals.
    """
    cfg = world.cfg
    eaten = cfg.goods[good].eaten_per_tick
    seller = world.agents[offer.seller]
    tie = world.get_edge(buyer.id, seller.id, Layer.SOCIAL)
    if not cfg.mechanisms.gifting or eaten <= 0 or offer.broker or tie is None:
        return None
    if buyer.inventory[good] >= eaten:
        return None  # not starving
    could_give = seller.inventory[good] - cfg.trade.help_keeps_ticks * eaten
    if could_give < cfg.trade.min_amount:
        return None
    if tie.strength >= cfg.trade.gift_min_strength:
        gift = min(cfg.trade.gift_amount, could_give)
        _move_goods(seller, buyer, good, gift)
        cause = f"{buyer.name} was starving; {seller.name} is a close friend"
        return _interaction(buyer, offer, good, gift, "gift", cause)
    cause = (
        f"{buyer.name} was starving; {seller.name} had {seller.inventory[good]:.0f} {good} "
        "but kept it"
    )
    return _interaction(buyer, offer, good, 0.0, "refused", cause)


def _move_goods(seller: Agent, buyer: Agent, good: str, quantity: float) -> None:
    seller.inventory[good] -= quantity
    buyer.inventory[good] += quantity


def _interaction(
    buyer: Agent, offer: Offer, good: str, amount: float, outcome: str, cause: str
) -> Interaction:
    return Interaction(buyer.id, offer.seller, good, amount, outcome, cause, broker=offer.broker)
