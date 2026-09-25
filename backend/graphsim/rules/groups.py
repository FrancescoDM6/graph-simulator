"""Tick phase 6: agents found, join and leave organizations; tiny organizations dissolve.

Membership is just an edge on the membership layer. An agent belongs to at most one org.
Being in an org keeps social ties with fellow members from decaying and lets members trade
with each other across towns.
"""

from graphsim.events import ids
from graphsim.model import Agent, Layer, Org, World, edge_key


def update_memberships(world: World) -> None:
    if not world.cfg.mechanisms.organizations:
        return
    agents = list(world.agents.values())
    world.rng.shuffle(agents)
    for agent in agents:
        org_id = world.org_of(agent.id)
        if org_id:
            _maybe_leave(world, agent, org_id)
        elif not _maybe_join(world, agent):
            _maybe_found(world, agent)
    _dissolve_small_orgs(world)


def _maybe_leave(world: World, agent: Agent, org_id: str) -> None:
    fellows = [m for m in world.members_of(org_id) if m != agent.id]
    known_trust = [t for t in (world.trust(agent.id, m) for m in fellows) if t is not None]
    if not known_trust:
        cause = "no longer knows any fellow member"
    else:
        average = sum(known_trust) / len(known_trust)
        if average >= world.cfg.organizations.leave_below_trust:
            return
        cause = f"average trust in fellow members fell to {average:.2f}"
    world.remove_edge(edge_key(agent.id, org_id, Layer.MEMBERSHIP))
    world.log.add(
        world.tick,
        "left_org",
        (agent.id, org_id),
        f"{agent.name} left {world.name(org_id)}",
        cause=cause,
        caused_by=_events_with(world, agent.id, ("distrusted", "refused"), fellows),
    )


def _maybe_join(world: World, agent: Agent) -> bool:
    """Joins the org whose members the agent trusts most in total, if that's enough."""
    best_org, best_score, best_friends = "", 0.0, []
    for org_id in world.orgs:
        trusted: list[tuple[float, str]] = []
        for member in world.members_of(org_id):
            trust = world.trust(agent.id, member)
            if trust is not None:
                trusted.append((trust, member))
        score = sum(t for t, _ in trusted)
        if score > best_score:
            best_org, best_score = org_id, score
            best_friends = [m for _, m in sorted(trusted, reverse=True)[:2]]
    if best_score < world.cfg.organizations.join_score:
        return False

    world.add_edge(agent.id, best_org, Layer.MEMBERSHIP)
    friend_names = " and ".join(world.name(m) for m in best_friends)
    world.log.add(
        world.tick,
        "joined_org",
        (agent.id, best_org),
        f"{agent.name} joined {world.name(best_org)}",
        cause=f"trusts members such as {friend_names} (total trust {best_score:.2f})",
        caused_by=_events_with(world, agent.id, ("trusted",), best_friends),
    )
    return True


def _maybe_found(world: World, agent: Agent) -> None:
    """An agent with enough trusted, unaffiliated friends may start an org with them."""
    cfg = world.cfg.organizations
    if len(world.orgs) >= cfg.max_orgs:
        return
    friends = [
        tie.other(agent.id)
        for tie in world.edges_of(agent.id, Layer.SOCIAL)
        if tie.trust >= cfg.found_min_trust and world.org_of(tie.other(agent.id)) is None
    ]
    if len(friends) < cfg.found_min_friends or world.rng.random() >= cfg.found_chance:
        return

    org = Org(
        id=world.new_id("org"),
        name=f"{agent.name}'s {world.rng.choice(cfg.name_words)}",
        home=agent.home,
        founded=world.tick,
    )
    world.add_org(org)
    world.add_edge(agent.id, org.id, Layer.MEMBERSHIP)
    world.log.add(
        world.tick,
        "founded_org",
        (agent.id, org.id),
        f"{agent.name} founded {org.name}",
        cause=f"{agent.name} had {len(friends)} trusted friends outside any organization",
        caused_by=_events_with(world, agent.id, ("trusted",), friends),
    )
    for friend in friends:
        world.add_edge(friend, org.id, Layer.MEMBERSHIP)
        world.log.add(
            world.tick,
            "joined_org",
            (friend, org.id),
            f"{world.name(friend)} joined {org.name}",
            cause=f"founding member invited by {agent.name}",
        )


def _dissolve_small_orgs(world: World) -> None:
    for org in list(world.orgs.values()):
        members = world.members_of(org.id)
        if len(members) >= 2:
            continue
        world.log.add(
            world.tick,
            "org_dissolved",
            (org.id, *members),
            f"{org.name} dissolved",
            cause=f"only {len(members)} member(s) left",
            caused_by=ids(world.log.recent(org.id, ("left_org",), limit=3)),
        )
        world.remove_node(org.id)


def _events_with(
    world: World, agent_id: str, kinds: tuple[str, ...], others: list[str], limit: int = 3
) -> tuple[int, ...]:
    """Ids of the agent's most recent events of these kinds that also involve one of `others`."""
    others_set = set(others)
    found = [e for e in world.log.recent(agent_id, kinds, limit=50) if others_set & set(e.subjects)]
    return ids(found[:limit])
