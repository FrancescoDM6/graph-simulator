# Simulation Spec (Phase 0)

The graph *is* the world. There is no map, grid, or hidden state beyond the node and edge
attributes listed here. Every tunable number named below lives in `backend/graphsim/config.py`.

## Node types

| Kind  | Count at start | State |
|-------|----------------|-------|
| Agent | `n_agents` (~40) | `occupation`, `home` town, `food`, `ore`, `coin`, `hunger_ticks`, `need` |
| Town  | 3 | name |
| Site  | 4 (2 farms, 2 mines) | `site_kind`, `stock`, `capacity`, `regen` |
| Org   | 0 at start; founded by agents | name, `home` town, `founded` tick |

### Occupations and interdependence

- **Farmers** harvest food at farms. Each harvest uses `ore_per_harvest` ore (tools).
  Without ore, their yield drops to `farm_yield_no_tools`.
- **Miners** harvest ore at mines. They need food like everyone else.
- **Merchants** produce nothing. They buy food and ore from producers and resell them at a
  markup. Only merchants can reach agents in neighbouring towns, which makes them natural brokers.

Everyone eats `food_per_tick` every tick. Food spoils at `food_spoil_rate` per tick, so hoarding
it doesn't pay off; coin does not spoil.

### Geography

```
 Ashford ──road── Millbrook ──road── Stonehold
    │              │     │               │
 North Farm   South Farm  Copper Mine   Iron Mine
```

Ashford has only a farm and Stonehold has only a mine. This means Ashford's farmers must get ore
from Stonehold's miners through merchants, friends, or organisations.

## Edge layers

Every edge is keyed by `(a, b, layer)` with `a < b`. So two nodes can be connected on several
layers at once, making the graph *multiplex* from day one.

| Layer        | Connects        | Meaningful fields | Lifecycle |
|--------------|-----------------|-------------------|-----------|
| `social`     | agent–agent     | `strength` (0–1), `trust` (0–1) | Formed by meeting, introduction, or first trade. Decays unless used. |
| `trade`      | agent–agent     | `strength` = recent trade volume (0–1) | Formed by a successful trade. Decays quickly. |
| `membership` | agent–org       | `created` tick | Join/leave rules below. |
| `access`     | agent/site–town, town–town | `cost` | Static in the MVP. Merchants have access edges to their home town and its neighbours. |

## Who can trade with whom

An agent's **reachable partners** are the union of:
1. agents living in any town the agent has an `access` edge to,
2. the agent's `social` and `trade` neighbours (in any town),
3. fellow members of the agent's org.

## Tick order

This order is exactly what `engine.step()` runs, top to bottom.

1. **Consume.** Each agent eats; food spoils. An agent who couldn't eat gains a hunger tick. After
   `leave_after_hungry` hungry ticks the agent **leaves** (node and edges removed). With
   `arrival_chance` per tick, a **newcomer** arrives in the richest town and picks that town's
   best-paid occupation.
2. **Produce.** Sites regenerate (farms regenerate at `drought_regen_factor` during a drought).
   Workers harvest in shuffled order until the site's stock runs out. A drought lasting
   `drought_length` ticks starts every `drought_every` ticks.
3. **Evaluate needs.** Each agent's `need` is its most pressing shortage: `food`, `ore`
   (farmers), or `stock` (merchants restocking).
4. **Trade.** In seeded shuffled order, each agent with a need picks a supplier from its reachable
   partners. The choice is weighted by trust, and up to `max_trade_attempts` suppliers are tried.
   Price = base price × (1 + merchant markup if the seller is a merchant) × (1 − trust discount).
   Outcomes are recorded as *interactions*; they are not applied yet. If a starving buyer can't
   pay a close friend, the friend may give food as a **gift**.
5. **Relationships.** Interactions are applied: success raises trust and strength, and a seller
   with nothing to spare loses trust. All social and trade ties decay (except social ties between
   fellow org members). An agent with more than `max_social_ties` drops its weakest tie
   (attention limit).
6. **Groups.** Members leave an org when their average trust in fellow members falls below
   `leave_below_trust`. Non-members join the org whose members they trust most, if that total
   trust reaches `join_score`. An agent with at least `found_min_friends` trusted friends who are
   not in any org may **found** a new org. An org with fewer than 2 members **dissolves**.
7. **New ties.** Agents randomly meet people in their town (`meet_chance`). They are also
   introduced to a close friend's close friends (`intro_chance`, triadic closure).
8. **Prune.** Social and trade ties whose strength falls below `prune_below` disappear.
9. **Metrics.** Network metrics are recorded and structural events detected (see below).

The world owns one `random.Random(seed)`. All iteration happens over insertion-ordered dicts or
sorted lists, never over sets, so the same seed always produces the same history.

## Events and causes

Every event has `tick`, `kind`, `subjects` (entity ids), `message` and `cause`. The cause says
*why* in plain words, e.g. `"trade failed: Bob had no spare food"`. Routine successful trades are
counted in the metrics rather than logged; the log keeps the changes that explain history:

- trade ties starting and ending
- trust crossing into *trusted* or *distrusted*
- meetings, introductions, and ties dropped or faded
- gifts, starving, leaving, arriving
- org founded, joined, left, dissolved
- drought start and end
- structural events (below)

## Metrics and structural events

Recorded every tick:
- population by occupation
- food and coin totals
- Gini coefficient of coin
- social density, components and clustering
- Louvain community count
- average trust
- trades, failures and gifts
- starving count and org count
- the top trade broker (trade-layer betweenness)
- the merchants' share of trade betweenness

Community labels are matched tick-to-tick by overlap (Jaccard), so colours stay stable.

Structural events are logged when:
- the social graph splits or merges (the component count changes),
- a community of at least `min_community_size` forms or dissolves,
- the Gini coefficient rises by more than `gini_jump` within `gini_window` ticks,
- a new agent becomes the top trade broker.

## Target phenomena

Tuning aims for these to appear without being scripted:

1. **Brokers:** merchants hold a disproportionate share of trade-layer betweenness.
2. **Factions:** the social graph settles into several communities, which split and merge over time.
3. **Drought shock:** average trust and trade drop during droughts, and organisations lose members.
4. **Inequality:** the Gini coefficient of coin drifts upward from the equal start.
