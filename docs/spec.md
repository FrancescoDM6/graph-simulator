# Simulation Spec

The graph *is* the world: agents, towns, work sites and organizations are nodes, and friendship,
trade, membership and access are edge layers. There is no map, grid or hidden state beyond the
node and edge attributes listed here.

**Every factor lives in [`scenario.toml`](../scenario.toml)**: the goods, sites and occupations
of the economy, the towns and roads, every parameter, mechanism switches, variants, experiments,
phenomenon thresholds, recording levels and the viewer's timeline. Names in `code` below are keys
in that file.

## The economy (data-driven)

- **Goods** (`[goods.*]`): anything with `eaten_per_tick > 0` must be eaten every tick, or the
  agent goes hungry. Goods spoil at `spoil_rate`. Agents keep a `reserve` of every good they eat
  or use as a tool, buy up to `buy_target` when below it, and sell only what is above it.
- **Site kinds** (`[site_kinds.*]`) produce one good, regenerate `regen` per tick up to
  `capacity`, and may be `drought_sensitive`.
- **Occupations** (`[occupations.*]`):
  - they work at a site kind next to their home town, producing `output` per tick;
  - they may use up `tool_use` of a `tool` good per harvest, and produce only
    `output_without_tool` without it;
  - they can `reach` their home town, or also its neighbours;
  - they may be `brokers`.

The default scenario:
- farmers grow food and use ore as tools;
- miners dig ore;
- merchants broker deals between towns;
- three towns lie in a line, Ashford – Millbrook – Stonehold. Ashford has no mine and
  Stonehold has no farm.

A new good, site kind or occupation needs no code, only entries in the file (tested in
`test_config.py`).

## Edge layers

Every edge is keyed by `(a, b, layer)`, so two nodes can be connected on several layers at once.

| Layer | Connects | Fields | Lifecycle |
|---|---|---|---|
| `social` | agent–agent | strength, trust | Formed by meeting, introduction or regular trading; decays unless used. |
| `trade` | agent–agent | strength = recent volume | Formed by a successful trade (brokered: buyer–broker and broker–seller); decays fast. |
| `membership` | agent–org | created | Join, leave, found, dissolve. |
| `access` | agent/site–town, town–town | cost | Home town; brokers also reach neighbouring towns. |

## Tick order (`engine.step`, top to bottom)

1. **Consume.** Goods spoil, then agents eat. After `leave_after_hungry` hungry ticks an agent
   leaves. Newcomers (`arrival_chance`) fill the job each town is most short of, compared with
   its `founding` mix.
2. **Produce.** Droughts start every `drought_every` ticks and last `drought_length`. Sites
   regenerate, and workers harvest in shuffled order.
3. **Evaluate needs.**
4. **Trade.** In shuffled order, buyers try up to `max_attempts` offers from producers they can
   meet, directly or through a broker they can meet.
   - **Choosing an offer.** Offers are weighted by trust and habit (`partner_choice` can replace
     this with random choice).
   - **Price.** Base price × (1 − `trust_discount` × trust), plus the broker's commission.
   - **Asking for help.** A starving buyer who can't trade asks an acquaintance who could spare
     food. A close friend gives it (a **gift**); anyone else **refuses**.
   - **Markets.** Prices then move with shortages and failed payments, and towns redistribute
     `town_levy` of residents' coin.
5. **Relationships.**
   - Trades strengthen ties, and regular partners become friends.
   - Gifts and trades raise trust; refusals lower it.
   - Each agent spends time with one friend.
   - Idle ties decay (except between fellow org members). The attention limit caps social ties
     at `max_social_ties`.
6. **Organizations.** Agents join, leave, found and dissolve orgs based on trust.
7. **New ties.** Chance meetings, and introductions to friends of friends (triadic closure),
   happen only between agents with room for another tie.
8. **Prune.** Faded ties disappear.
9. **Metrics.** Network measures are computed, community identities updated, and structural
   events detected.

One seeded random generator drives everything, and iteration never goes over sets. The same seed
and settings give the same history, which is tested across Python processes.

## Mechanism switches (`[mechanisms]`)

- `gifting`: with it off, starving agents don't ask for help, so there are no gifts and no
  refusals.
- `brokering`: off also removes broker occupations.
- `meetings`, `introductions`, `trade_friendships`, `organizations`, `droughts`,
  `price_adjustment`, `town_levy`, `attention_limit`.
- `social_dynamics`:
  - `dynamic`;
  - `frozen_topology`: no social tie added or removed after tick 0;
  - `frozen`: ties, strength and trust are all fixed.
- `partner_choice`:
  - `network`;
  - `random_reachable`: uniform among reachable partners;
  - `random_global`: any producer anywhere, with no brokers.

Each switch is tested to actually change behaviour (`test_mechanisms.py`). Ready-made ablations
are in `[variants.*]`.

## Events and causal trails

Every event has an id, `tick`, `kind`, `subjects`, a human-readable `message` and `cause`, and
`caused_by`: the ids of the earlier events that led to it. Some examples:

- `trusted` → the trade or gift that pushed trust over `trusted_above`;
- a gift → the recipient's `starving` event and the drought;
- `starving` → the agent's own failed purchases this hungry spell, and the drought;
- `left` → `starving`, and `arrived` → the departure that opened the job;
- org, community, network and price events → the tie changes or trade attempts behind them.

Every trade attempt is logged as a **detail event**, so trails are complete. Every change to
trust is recorded in a **trust ledger** together with the event that caused it.

> These are *recorded contributing causes*: what the rules knew about when they acted. They are
> a trail to follow, not proof. Whether a cause really matters is what ablations answer.

## Communities with identity

Louvain runs every `community_every` ticks. New communities are matched to living ones by member
overlap:

- **Continuation**: Jaccard ≥ `community_match_jaccard` keeps the old id.
- **Split**: a new group mostly drawn from one community becomes its child.
- **Merger**: an old group whose members mostly went to one new community dies, merged into it.
- **Birth** and **dissolution** cover everything else.

Each community keeps a record: born, died, fate, parent, merged-into, peak size, members ever and
turnover. Communities shorter-lived than `community_min_lifespan` count as detection flicker.

## Recording and runs

Every run is stored in the run database (`[run] database`, SQLite) and never overwritten.

- **`full` recording** (for the viewer) keeps per-tick snapshots and agent histories, detail
  events, the trust ledger and community membership. That's about 19 KB per tick.
- **`summary` recording** (for batch experiments) keeps metrics every 5 ticks, notable events,
  agent lifetimes and community records.

Identical runs are identified by config hash, seed, length and code version, and reused rather
than recomputed. Any summary run can be recomputed at full detail, and it is the same world.

## Measures and phenomena

`backend/graphsim/analysis.py` defines one number per run for each question: brokerage ratio,
community lifespan and turnover, drought ratios, Gini, trust, and so on. These are computed from
every tick while the run is computed, and can be recomputed later from storage with
`--reanalyze`. `[phenomena.*]` in the scenario turns a measure into a present/absent verdict.

## What the 100-seed ablation study found

`python -m graphsim.experiment ablations`: seeds 1–100 × 8 variants × 2000 ticks (800 runs,
about 19 minutes on 22 cores). "Paired" means compared with the baseline run of the same seed.

| Phenomenon (measure) | Baseline | What removes or changes it |
|---|---|---|
| **Brokerage** (broker share ÷ broker population share ≥ 2) | 100/100 worlds, median 7.7× | **Gone** without merchants (0/100) or with random partners (0/100). **Weakened** without droughts (77/100; lower in 96% of seeds). **Stronger** with a static social graph or without orgs (higher in 75–79% of seeds). |
| **Inequality** (final Gini ≥ 0.4) | 100/100, median 0.60 | **Gone** without merchants (3/100): merchants are the inequality engine. Random partners reduce it (84/100; lower in 97% of seeds). |
| **Drought shock** (starvation ratio ≥ 2) | 100/100, median 4.7× | Gone without droughts, as it should be. **Also gone without merchants** (0/100). Over the first 30 seeds, starvation averages 1.65 outside droughts and 1.40 inside them, compared with 1.15 and 6.06 at baseline. Two readings are possible: brokered trade spreads a local drought into widespread hunger, or the people brokers keep fed in normal times are the ones who starve in droughts. `no_merchants` also shrinks the population, so a follow-up variant that keeps the population equal is needed to tell these apart. |
| **Drought solidarity** (gifts in droughts ≥ 3×) | 100/100, median 13× | Requires droughts and gifting (by construction), and also merchants (0/100 without). A static social graph weakens it (lower in 94% of seeds). |
| **Factions** (mean communities ≥ 2) | 100/100 | 100/100 in every variant. **This measure doesn't discriminate**: communities largely mirror the three towns. A better factions measure is future work. |

Other results:

- **Droughts build the social structure.** Communities formed mid-run live a median of 78 ticks
  at baseline, but only about 6 without droughts (mostly flicker). Average trust is 0.89 at
  baseline, 0.66 without gifting and 0.59 without droughts. Trust is high *because* hard times
  produce gifts.
- **Null result: introductions (triadic closure)** make no measurable difference to any
  phenomenon at this scale.
