"""The tick loop. Read `step` top to bottom to see exactly what happens each tick."""

from graphsim import metrics
from graphsim.events import Event
from graphsim.model import World
from graphsim.rules import groups, needs, production, relationships, trade


def step(world: World) -> list[Event]:
    """Advances the world one tick and returns the events that happened during it."""
    world.tick += 1
    first_event = len(world.log)
    world.interactions.clear()

    # 1. Consume: eat, starve, leave, arrive
    needs.consume_food(world)
    needs.maybe_add_newcomer(world)

    # 2. Produce
    production.update_season(world)
    production.regenerate_sites(world)
    production.harvest(world)

    # 3. Evaluate needs
    needs.evaluate_needs(world)

    # 4. Trade (records interactions; doesn't change relationships yet)
    trade.run_trading(world)

    # 5. Relationships
    relationships.apply_interactions(world)
    relationships.socialize(world)
    relationships.decay_ties(world)
    relationships.enforce_attention_limit(world)

    # 6. Groups
    groups.update_memberships(world)

    # 7. New ties
    relationships.form_new_ties(world)

    # 8. Prune
    relationships.prune_faded_ties(world)

    # 9. Metrics and structural events
    metrics.record_tick(world)

    return world.log.since(first_event)
