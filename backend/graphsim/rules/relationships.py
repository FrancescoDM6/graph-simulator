"""Tick phases 5, 7 and 8: how ties strengthen, weaken, form, and disappear.

Trust changes only through trade (successes, gifts, refusals to help) and introductions.
Strength is about contact: it grows with trades and time spent together, and decays otherwise.
"""

from graphsim.model import Edge, Interaction, Layer, World

# --- Phase 5: relationships -------------------------------------------------------------------


def apply_interactions(world: World) -> None:
    for interaction in world.interactions:
        if interaction.outcome == "success":
            _on_trade_success(world, interaction)
        elif interaction.outcome == "gift":
            _on_gift(world, interaction)
        elif interaction.outcome == "refused":
            _on_refusal(world, interaction)
        # "no_surplus" and "cannot_afford" are nobody's fault: no trust change.


def socialize(world: World) -> None:
    """Each agent spends time with one friend, favouring stronger ties (limited attention)."""
    for agent_id in list(world.agents):
        ties = world.edges_of(agent_id, Layer.SOCIAL)
        if not ties:
            continue
        tie = world.rng.choices(ties, [t.strength for t in ties])[0]
        tie.strength = min(1.0, tie.strength + world.cfg.socialize_bump)
        tie.last_active = world.tick


def decay_ties(world: World) -> None:
    """Unused ties weaken. Social ties between fellow org members are kept up by the org."""
    cfg = world.cfg
    for edge in world.edges.values():
        if edge.last_active == world.tick:
            continue
        if edge.layer == Layer.SOCIAL and not _fellow_members(world, edge.a, edge.b):
            edge.strength *= 1 - cfg.social_decay
        elif edge.layer == Layer.TRADE:
            edge.strength *= 1 - cfg.trade_decay


def enforce_attention_limit(world: World) -> None:
    limit = world.cfg.max_social_ties
    for agent in list(world.agents.values()):
        ties = world.edges_of(agent.id, Layer.SOCIAL)
        if len(ties) <= limit:
            continue
        # Weakest first; the other agent's id breaks ties so the order is deterministic.
        ties.sort(key=lambda t: (t.strength, t.other(agent.id)))
        for tie in ties[: len(ties) - limit]:
            other = tie.other(agent.id)
            world.log.add(
                world.tick,
                "tie_dropped",
                (agent.id, other),
                f"{agent.name} drifted apart from {world.name(other)}",
                cause=f"{agent.name} only has room for {limit} ties and this was the weakest",
            )
            world.remove_edge(tie.key)


# --- Phase 7: new ties ------------------------------------------------------------------------


def form_new_ties(world: World) -> None:
    """Chance meetings and introductions, only between agents with room for another tie."""
    cfg = world.cfg
    for agent_id in list(world.agents):
        if world.rng.random() < cfg.meet_chance and _has_room_for_tie(world, agent_id):
            _meet_townsperson(world, agent_id)
        if world.rng.random() < cfg.intro_chance and _has_room_for_tie(world, agent_id):
            _introduce_friend_of_friend(world, agent_id)


# --- Phase 8: prune ---------------------------------------------------------------------------


def prune_faded_ties(world: World) -> None:
    for edge in list(world.edges.values()):
        if edge.layer not in (Layer.SOCIAL, Layer.TRADE) or edge.strength >= world.cfg.prune_below:
            continue
        a, b = world.name(edge.a), world.name(edge.b)
        if edge.layer == Layer.SOCIAL:
            kind, message = "tie_faded", f"{a} and {b} lost touch"
            cause = f"no contact since tick {edge.last_active}"
        else:
            kind, message = "trade_ended", f"{a} and {b} stopped trading"
            cause = f"no trades since tick {edge.last_active}"
        world.log.add(world.tick, kind, (edge.a, edge.b), message, cause)
        world.remove_edge(edge.key)


# --- helpers ----------------------------------------------------------------------------------


def _on_trade_success(world: World, interaction: Interaction) -> None:
    """A brokered deal ties buyer to broker and broker to seller; otherwise buyer to seller."""
    if interaction.broker:
        _record_trade(world, interaction.buyer, interaction.broker, interaction.cause)
        _record_trade(world, interaction.broker, interaction.seller, interaction.cause)
    else:
        _record_trade(world, interaction.buyer, interaction.seller, interaction.cause)


def _record_trade(world: World, buyer: str, seller: str, cause: str) -> None:
    cfg = world.cfg
    trade_tie = world.get_edge(buyer, seller, Layer.TRADE)
    if trade_tie is None:
        trade_tie = world.add_edge(buyer, seller, Layer.TRADE, strength=0.0)
        world.log.add(
            world.tick,
            "trade_started",
            (buyer, seller),
            f"{world.name(buyer)} started trading with {world.name(seller)}",
            cause=cause,
        )
    trade_tie.strength = min(1.0, trade_tie.strength + cfg.trade_bump)
    trade_tie.last_active = world.tick

    # Regular trading partners get to know each other, if both have room for another tie.
    # Trust lives on the social tie.
    social_tie = world.get_edge(buyer, seller, Layer.SOCIAL)
    if (
        social_tie is None
        and trade_tie.strength >= cfg.trade_friendship_at
        and _has_room_for_tie(world, buyer)
        and _has_room_for_tie(world, seller)
    ):
        social_tie = _get_or_create_social_tie(world, buyer, seller)
        world.log.add(
            world.tick,
            "met",
            (buyer, seller),
            f"{world.name(buyer)} got to know {world.name(seller)}",
            cause="they became regular trading partners",
        )
    if social_tie is not None:
        social_tie.strength = min(1.0, social_tie.strength + cfg.social_bump)
        social_tie.last_active = world.tick
        _change_trust(world, social_tie, cfg.trust_gain * (1 - social_tie.trust), cause)


def _on_gift(world: World, interaction: Interaction) -> None:
    cfg = world.cfg
    world.log.add(
        world.tick,
        "gift",
        (interaction.seller, interaction.buyer),
        f"{world.name(interaction.seller)} gave {interaction.amount:.1f} food "
        f"to {world.name(interaction.buyer)}",
        cause=interaction.cause,
    )
    tie = _get_or_create_social_tie(world, interaction.buyer, interaction.seller)
    tie.strength = min(1.0, tie.strength + cfg.social_bump)
    tie.last_active = world.tick
    _change_trust(world, tie, 2 * cfg.trust_gain * (1 - tie.trust), interaction.cause)


def _on_refusal(world: World, interaction: Interaction) -> None:
    tie = world.get_edge(interaction.buyer, interaction.seller, Layer.SOCIAL)
    if tie is not None:
        _change_trust(world, tie, -world.cfg.trust_loss, interaction.cause)


def _change_trust(world: World, tie: Edge, delta: float, cause: str) -> None:
    """Changes trust and logs an event when it crosses into 'trusted' or 'distrusted'."""
    cfg = world.cfg
    before = tie.trust
    tie.trust = min(1.0, max(0.0, before + delta))
    a, b = world.name(tie.a), world.name(tie.b)
    if before < cfg.trusted_above <= tie.trust:
        world.log.add(
            world.tick, "trusted", (tie.a, tie.b), f"{a} and {b} now trust each other", cause
        )
    elif before >= cfg.distrusted_below > tie.trust:
        world.log.add(
            world.tick, "distrusted", (tie.a, tie.b), f"{a} and {b} lost trust in each other", cause
        )


def _get_or_create_social_tie(world: World, a: str, b: str) -> Edge:
    cfg = world.cfg
    tie = world.get_edge(a, b, Layer.SOCIAL)
    if tie is None:
        tie = world.add_edge(
            a, b, Layer.SOCIAL, strength=cfg.meet_strength, trust=cfg.initial_trust
        )
    return tie


def _has_room_for_tie(world: World, agent_id: str) -> bool:
    return len(world.edges_of(agent_id, Layer.SOCIAL)) < world.cfg.max_social_ties


def _fellow_members(world: World, a: str, b: str) -> bool:
    org = world.org_of(a)
    return org is not None and org == world.org_of(b)


def _meet_townsperson(world: World, agent_id: str) -> None:
    cfg = world.cfg
    home = world.agents[agent_id].home
    already_known = set(world.neighbors(agent_id, Layer.SOCIAL))
    strangers = [
        a
        for a in world.agents_in_town(home)
        if a != agent_id and a not in already_known and _has_room_for_tie(world, a)
    ]
    if not strangers:
        return
    other = world.rng.choice(strangers)
    world.add_edge(
        agent_id, other, Layer.SOCIAL, strength=cfg.meet_strength, trust=cfg.initial_trust
    )
    world.log.add(
        world.tick,
        "met",
        (agent_id, other),
        f"{world.name(agent_id)} met {world.name(other)}",
        cause=f"both live in {world.name(home)}",
    )


def _introduce_friend_of_friend(world: World, agent_id: str) -> None:
    """Triadic closure: a close friend introduces the agent to one of their close friends."""
    cfg = world.cfg
    close_friends = _close_friends(world, agent_id)
    if not close_friends:
        return
    friend = world.rng.choice(close_friends)
    already_known = set(world.neighbors(agent_id, Layer.SOCIAL))
    candidates = [
        f
        for f in _close_friends(world, friend)
        if f != agent_id and f not in already_known and _has_room_for_tie(world, f)
    ]
    if not candidates:
        return
    other = world.rng.choice(candidates)
    # They start out trusting each other about as much as they each trust the go-between.
    trust = (world.trust(agent_id, friend) + world.trust(friend, other)) / 2
    world.add_edge(agent_id, other, Layer.SOCIAL, strength=cfg.meet_strength, trust=trust)
    world.log.add(
        world.tick,
        "introduced",
        (agent_id, other, friend),
        f"{world.name(friend)} introduced {world.name(agent_id)} to {world.name(other)}",
        cause=f"both are close to {world.name(friend)}",
    )


def _close_friends(world: World, agent_id: str) -> list[str]:
    return [
        tie.other(agent_id)
        for tie in world.edges_of(agent_id, Layer.SOCIAL)
        if tie.strength >= world.cfg.intro_min_strength
    ]
