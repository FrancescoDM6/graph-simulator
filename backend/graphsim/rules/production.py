"""Tick phase 2: seasons, site regeneration, and harvesting."""

from graphsim.model import Agent, Layer, Site, World


def update_season(world: World) -> None:
    """A drought of `drought_length` ticks begins every `drought_every` ticks, unless an
    intervention brought one on or ended one early (interventions.py)."""
    seasons = world.cfg.seasons
    phase = world.tick % seasons.drought_every
    in_drought = (
        world.cfg.mechanisms.droughts
        and world.tick >= seasons.drought_every
        and phase < seasons.drought_length
    )
    forced = world.tick <= world.forced_drought_until
    if forced:
        in_drought = True
    elif world.tick <= world.drought_suppressed_until:
        in_drought = False
    if in_drought and not world.drought:
        world.drought = True
        event = world.log.add(
            world.tick,
            "drought_started",
            (),
            "A drought began",
            cause="brought on by an intervention" if forced else "the dry season",
            caused_by=(world.drought_intervention,) if forced else (),
        )
        world.drought_event = event.id
    elif not in_drought and world.drought:
        world.drought = False
        world.log.add(
            world.tick,
            "drought_ended",
            (),
            "The drought ended",
            cause="rain returned",
            caused_by=(world.drought_event,) if world.drought_event is not None else (),
        )
        world.drought_event = None


def regenerate_sites(world: World) -> None:
    for site in world.sites.values():
        regen = site.regen
        if world.drought and world.cfg.site_kinds[site.kind].drought_sensitive:
            regen *= world.cfg.seasons.drought_regen_factor
        site.stock = min(site.capacity, site.stock + regen)


def harvest(world: World) -> None:
    """Workers take from sites next to their home town, in shuffled order, until stock runs out."""
    cfg = world.cfg
    workers = [a for a in world.agents.values() if cfg.occupations[a.occupation].works_at]
    world.rng.shuffle(workers)
    for agent in workers:
        site = _workplace(world, agent)
        good = cfg.produced_by(agent.occupation)
        if site is None or agent.inventory[good] >= cfg.goods[good].max_holding:
            continue  # nowhere to work, or already holding more than they can sell
        taken = min(_output(world, agent), site.stock)
        site.stock -= taken
        agent.inventory[good] += taken
        world.record_flow(agent.id, good, taken, "harvest")


def _workplace(world: World, agent: Agent) -> Site | None:
    """The site in the agent's home town that matches its occupation and has the most stock."""
    kind = world.cfg.occupations[agent.occupation].works_at
    sites = [
        world.sites[n]
        for n in world.neighbors(agent.home, Layer.ACCESS)
        if n in world.sites and world.sites[n].kind == kind
    ]
    return max(sites, key=lambda s: s.stock, default=None)


def _output(world: World, agent: Agent) -> float:
    """How much one harvest yields. Occupations with a tool use some of it up each harvest,
    and produce less without it."""
    occupation = world.cfg.occupations[agent.occupation]
    if not occupation.tool:
        return occupation.output
    if agent.inventory[occupation.tool] >= occupation.tool_use:
        agent.inventory[occupation.tool] -= occupation.tool_use
        world.record_flow(agent.id, occupation.tool, -occupation.tool_use, "tool_use")
        return occupation.output
    return occupation.output_without_tool
