"""Tick phase 2: seasons, site regeneration, and harvesting."""

from graphsim.model import Agent, Layer, Occupation, Site, SiteKind, World


def update_season(world: World) -> None:
    """A drought of `drought_length` ticks begins every `drought_every` ticks."""
    cfg = world.cfg
    phase = world.tick % cfg.drought_every
    in_drought = world.tick >= cfg.drought_every and phase < cfg.drought_length
    if in_drought and not world.drought:
        world.drought = True
        world.log.add(
            world.tick, "drought_started", (), "A drought began", cause="the dry season"
        )
    elif not in_drought and world.drought:
        world.drought = False
        world.log.add(world.tick, "drought_ended", (), "The drought ended", cause="rain returned")


def regenerate_sites(world: World) -> None:
    for site in world.sites.values():
        regen = site.regen
        if site.kind == SiteKind.FARM and world.drought:
            regen *= world.cfg.drought_regen_factor
        site.stock = min(site.capacity, site.stock + regen)


def harvest(world: World) -> None:
    """Workers take from sites next to their home town, in shuffled order, until stock runs out."""
    workers = [a for a in world.agents.values() if a.occupation != Occupation.MERCHANT]
    world.rng.shuffle(workers)
    for agent in workers:
        site = _workplace(world, agent)
        if site is None:
            continue
        wanted = _yield(world, agent)
        taken = min(wanted, site.stock)
        site.stock -= taken
        if agent.occupation == Occupation.FARMER:
            agent.food += taken
        else:
            agent.ore += taken


def _workplace(world: World, agent: Agent) -> Site | None:
    """The site in the agent's home town that matches its occupation and has the most stock."""
    kind = SiteKind.FARM if agent.occupation == Occupation.FARMER else SiteKind.MINE
    sites = [
        world.sites[n]
        for n in world.neighbors(agent.home, Layer.ACCESS)
        if n in world.sites and world.sites[n].kind == kind
    ]
    return max(sites, key=lambda s: s.stock, default=None)


def _yield(world: World, agent: Agent) -> float:
    cfg = world.cfg
    if agent.occupation == Occupation.MINER:
        return cfg.mine_yield
    # Farmers wear out tools: each harvest uses some ore, and without it they harvest less.
    if agent.ore >= cfg.ore_per_harvest:
        agent.ore -= cfg.ore_per_harvest
        return cfg.farm_yield
    return cfg.farm_yield_no_tools
