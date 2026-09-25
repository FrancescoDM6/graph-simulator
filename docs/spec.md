# Simulation Spec (Phase 0)

The graph *is* the world. There is no map, grid, or hidden state beyond the node and edge
attributes listed here. Every tunable number named below lives in `backend/graphsim/config.py`.
The founding population of each town is in `backend/graphsim/world_gen.py` (`TOWNS`).

## Node types

| Kind  | Count at start | State |
|-------|----------------|-------|
| Agent | 33 (see `TOWNS`) | `occupation`, `home` town, `food`, `ore`, `coin`, `hunger_ticks`, `need` |
| Town  | 3 | name, founding mix of occupations |
| Site  | 4 (2 farms, 2 mines) | `site_kind`, `stock`, `capacity`, `regen` |
| Org   | 0 at start; founded by agents | name, `home` town, `founded` tick |

### Occupations and interdependence

- **Farmers** harvest food at a farm next to their town. Each harvest uses `ore_per_harvest` ore
  (tools). Without ore they still farm, but only at `farm_yield_no_tools`.
- **Miners** harvest ore at a mine next to their town. They need food like everyone else.
- **Merchants** produce nothing and hold no stock. They **broker** deals between buyers and
  producers who can't meet directly, taking `merchant_markup` of the price as commission.
  Merchants can reach their home town and its neighbours, so they are the only link between
  Ashford and Stonehold.

Everyone eats `food_per_tick` each tick. Food spoils at `food_spoil_rate`. Producers stop
harvesting once they hold `max_holding` of their good.

### Geography

```
 Ashford ──road── Millbrook ──road── Stonehold
    │              │     │               │
 North Farm   South Farm  Copper Mine   Iron Mine
 12 farmers    9 farmers, 3 miners      5 miners
 1 merchant    2 merchants              1 merchant
```

Ashford has no mine and Stonehold has no farm. Ashford's farmers get tools, and Stonehold's
miners get food, through merchants, friends, or organisations.

## Edge layers

Every edge is keyed by `(a, b, layer)` with `a < b`. So two nodes can be connected on several
layers at once, making the graph *multiplex* from day one.

| Layer        | Connects        | Meaningful fields | Lifecycle |
|--------------|-----------------|-------------------|-----------|
| `social`     | agent–agent     | `strength` (0–1), `trust` (0–1) | Formed by meeting, introduction, or regular trading. Decays unless used. |
| `trade`      | agent–agent     | `strength` = recent trade volume (0–1) | Formed by a successful trade (brokered trades link buyer–broker and broker–seller). Decays quickly. |
| `membership` | agent–org       | `created` tick | Join/leave rules below. |
| `access`     | agent/site–town, town–town | `cost` | Agents reach their home town; merchants also reach neighbouring towns. |

## Who can trade with whom

An agent can **meet**:
1. anyone with access to a town the agent has access to (residents plus visiting merchants),
2. its `social` and `trade` neighbours (in any town),
3. fellow members of its org.

A buyer's **offers** are the producers it can meet directly, plus producers that a merchant it
can meet can meet (brokered).

## Tick order

This order is exactly what `engine.step()` runs, top to bottom.

1. **Consume.** Agents eat; food spoils. An agent who can't eat gains a hunger tick. After
   `leave_after_hungry` hungry ticks it **leaves** (node and edges removed). With
   `arrival_chance` per tick, a **newcomer** fills the job its town is most short of,
   compared with the founding mix.
2. **Produce.** A drought lasting `drought_length` ticks starts every `drought_every` ticks,
   and farm regeneration drops to `drought_regen_factor`. Sites regenerate. Workers harvest
   in shuffled order until the site's stock runs out.
3. **Evaluate needs.** Each agent needs `food` below `food_reserve`; farmers also need `ore`
   below `ore_reserve`.
4. **Trade.** In seeded shuffled order, each agent with a need tries up to
   `max_trade_attempts` offers. Offers are picked with weight = trust in the contact (or
   `stranger_weight`), plus trade-tie strength (habit). Brokered offers are weighted by
   `brokered_weight`.
   - **Price** = base price × (1 − `trust_discount` × trust), plus the broker's commission.
   - If a *hungry* buyer can't trade with someone it knows who could spare food, it asks for
     help. A close friend (tie strength ≥ `gift_min_strength`) gives food; anyone else
     **refuses**.
   - Outcomes are recorded as *interactions*.
   - Then the **market** reacts. Each good's base price rises when buyers find nothing to
     spare, and falls when they can't pay (by up to `price_adjust_rate` per tick). Each town
     also takes `town_levy` of every resident's coin and splits it equally among residents,
     which keeps money circulating.
5. **Relationships.** Interactions are applied:
   - A successful trade strengthens trade ties. Once a trade tie is strong
     (`trade_friendship_at`), the partners also form a social tie, if both have room.
   - Successes and gifts raise trust; refusals lower it.
   - Each agent spends time with one friend (weighted by strength), which bumps that tie.
   - Idle ties decay, except social ties between fellow org members.
   - An agent with more than `max_social_ties` drops its weakest tie (attention limit).
6. **Groups.**
   - Members leave when their average trust in fellow members falls below `leave_below_trust`.
   - Non-members join the org whose members they trust most, if that total reaches `join_score`.
   - An agent with at least `found_min_friends` trusted, unaffiliated friends may **found** an
     org with them.
   - An org with fewer than 2 members **dissolves**.
7. **New ties.** Agents randomly meet people in their town (`meet_chance`). They are also
   introduced to a close friend's close friends (`intro_chance`, triadic closure).
8. **Prune.** Social and trade ties weaker than `prune_below` disappear.
9. **Metrics.** Network metrics are recorded and structural events detected (see below).

The world owns one `random.Random(seed)`. All iteration happens over insertion-ordered dicts or
sorted lists, never over sets, so the same seed always produces the same history.

## Events and causes

Every event has `tick`, `kind`, `subjects` (entity ids), `message` and `cause`. The cause says
*why* in plain words, e.g. `"Rhea was starving; Bob had 9 food but kept it"`. Routine
successful trades are counted in the metrics rather than logged; the log keeps the changes that
explain history:

- trade ties starting and ending
- trust crossing into *trusted* or *distrusted*
- meetings, introductions, and ties dropped or faded
- gifts, starving, leaving, arriving
- org founded, joined, left, dissolved
- price rose or fell; drought started or ended
- structural events (below)

## Metrics and structural events

Recorded every tick:
- population by occupation
- food and coin totals, and prices
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
- the social graph splits or merges (the count of components with at least
  `min_component_size` agents changes),
- a community of at least `min_community_size` forms or dissolves,
- the Gini coefficient rises by more than `gini_jump` within `gini_window` ticks,
- a new agent clearly overtakes the top trade broker.

## Target phenomena

These are what tuning aimed for. `python -m graphsim.cli` reports all four.

1. **Brokers.** Merchants hold a disproportionate share of trade-layer betweenness. *Observed
   (seeds 1–3):* 50–85% of betweenness from about 10% of the population. One merchant usually
   becomes dominant, because buyers return to regular partners.
2. **Factions.** The social graph forms communities that split and merge over time.
   *Observed:* 2–4 communities, with a few formation/dissolution events per 100 ticks.
3. **Drought shock.** *Hypothesis was:* trust collapses during droughts. *Observed instead:*
   - starvation rises about 6× and departures about 4×,
   - new trade ties double as the network reroutes,
   - gifts between close friends rise about 100×, so average trust goes *up*.

   Droughts produce mutual aid, not distrust. Refusals, which lower trust, stay rare.
4. **Inequality.** The Gini coefficient of coin rises from 0 to roughly 0.5–0.7.
