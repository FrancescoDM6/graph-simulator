# Simulation Spec

The graph *is* the world: agents, towns, work sites and organizations are nodes, and friendship,
trade, membership and access are edge layers. There is no map, grid or hidden state beyond the
node and edge attributes listed here.

**Every factor lives in [`scenario.toml`](../scenario.toml)**: the goods, sites and occupations
of the economy, every parameter, mechanism switches, variants, experiments, phenomenon
thresholds, recording levels and the viewer's timeline. **The world it runs in** (towns, their
sites and founding people, roads) is one of the files in [`scenarios/`](../scenarios). Names in
`code` below are keys in those files.

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

The default economy:
- farmers grow food and use ore as tools;
- miners dig ore;
- merchants broker deals between towns.

A new good, site kind or occupation needs no code, only entries in the file (tested in
`test_config.py`).

## Worlds (`scenarios/`)

Each file in `scenarios/` is a world: a `title`, a `description`, and either a written-out map
(`[world.towns.*]` with a `position`, `sites` and `founding` people, plus `[[world.roads]]`) or a
`[generator]` with a few parameters that writes the map (`backend/graphsim/generators.py`). A
world file may also change any other setting, the way a variant does. `[run] scenario` names the
default world.

- **Sites** have a `scale`: their capacity and regrowth as a multiple of their kind's. It lets a
  map split a farm's worth of land over several villages.
- **Towns** have a `position` on the map (0..1). The viewer draws the map from it and starts the
  graph in that shape.
- **Reach is one road hop.** Producers trade in their home town; merchants reach home and the
  towns one road away, and broker between them (`rules/trade.py`). Road `cost` is stored but no
  rule reads it.
- **Generated worlds are deterministic.** A map depends only on its parameters, never on the
  run's seed, so different seeds vary what the agents do, not where they live.
- **Every generated world has the same totals** (`[layout]`): the same 33 people by occupation
  (21 farmers, 8 miners, 4 merchants) and the same capacity of each site kind (2 standard
  farms, 2 standard mines). Worlds differ in shape, not size. `python -m graphsim.scenarios`
  prints every world's totals and road-map shape, so any other difference is visible.

| World | Map | Merchants live |
|---|---|---|
| `three_towns` (default) | Three towns in a line: a farming town, a mixed town, a mining town. | 1 / 2 / 1 |
| `hub_and_spokes` | A central market town joined to 4 spokes (2 farming, 2 mining); no road between spokes. | all in the hub |
| `two_regions` | Two regions of 2 towns, fully connected inside, joined by `bridges` roads; each region has a farm and a mine. | at the bridge ends, or in every town (`merchants`) |
| `isolated_villages` | 8 villages in a chain, each beside one half-size farm or mine. | every other village |
| `resource_imbalance` | `two_regions` with all the farms in the West and all the mines in the East. | at the bridge ends |
| `merchant_economy` | `three_towns` with 8 merchants and 17 farmers (same 33 people). | 2 / 4 / 2 |

Experiments cross worlds with variants (`scenarios = [...]`), and sweeps can set generator
parameters (`"generator.bridges" = [1, 2, 3, 4]`). A world is its scenario plus its generator
parameters, and **runs are only paired by seed within one world**: the same seed on a different
map is a different world, so worlds are compared by their distributions.

## Edge layers

Every edge is keyed by `(a, b, layer)`, so two nodes can be connected on several layers at once.

| Layer | Connects | Fields | Lifecycle |
|---|---|---|---|
| `social` | agent–agent | strength, trust | Formed by meeting, introduction or regular trading; decays unless used. |
| `trade` | agent–agent | strength = recent volume | Formed by a successful trade (brokered: buyer–broker and broker–seller); decays fast. |
| `membership` | agent–org | created | Join, leave, found, dissolve. |
| `access` | agent/site–town, town–town | cost | Home town; brokers also reach neighbouring towns. |

## Tick order (`engine.step`, top to bottom)

0. **Interventions** scheduled for this tick, if any (see *Interventions and branches*).
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

## The resource ledger

Every movement of coin or goods is recorded as a `Flow` with an agent, asset, signed amount,
category, counterparty and the event that caused it. The categories are:

| Category | Recorded in |
|---|---|
| endowment | `world_gen.create_agent` |
| harvest, tool_use | `rules/production.py` |
| eaten, spoiled | `rules/needs.py` |
| departure | `rules/needs.py` (what an agent takes when it leaves) |
| sale, purchase, commission, gift_given, gift_received | `rules/trade.py` |
| levy_paid, levy_received | `rules/market.py` |

A brokered sale records the buyer's purchase, the seller's sale and the broker's commission (its
counterparty is `buyer>seller`).

`test_ledger.py` checks that the ledger is complete. For every agent, asset and tick, the flows
sum exactly to the change in holdings, in several variants. Anything that moves resources
without a flow fails this test.

## Milestones

`milestones.py` turns the ledger into explanations. An agent's standing changes when it holds
at least `wealthy_ratio` × the median agent's coin (wealthy), at most `poor_ratio` × the median
(poor), or has at least `hub_ratio` × the median number of ties (hub). A `became_*` or
`no_longer_*` event is logged once the change has lasted `status_hold` ticks. Ratios to the
median are used rather than ranks, so nobody "becomes wealthy" while everyone holds the same.

Each milestone's `cause` summarizes the agent's ledger over the last `attribution_window` ticks,
e.g. "earned 689 coin (commission 97% from 76 pairs); spent 634 (levy 74%, purchase 26%)".
Its `caused_by` points at the largest trades and gifts behind it. So the trail
wealthy ← commissions ← these brokered trades is built from records only. Milestones run in the
metrics phase and only read the world: a seed's behaviour is identical with or without them.

## Communities with identity

Louvain runs every `community_every` ticks. New communities are matched to living ones by member
overlap:

- **Continuation**: Jaccard ≥ `community_match_jaccard` keeps the old id.
- **Split**: a new group mostly drawn from one community becomes its child.
- **Merger**: an old group whose members mostly went to one new community dies, merged into it.
- **Birth** and **dissolution** cover everything else.

Each community keeps a record: born, died, fate, parent, merged-into, peak size, members ever and
turnover. Communities shorter-lived than `community_min_lifespan` count as detection flicker.
At full recording, each detection also stores the community's internal density, mean internal
trust and internal trade. Organizations get the same record every tick (`org_ticks`).

## Recording and runs

Every run is stored in the run database (`[run] database`, SQLite) and never overwritten.

- **`full` recording** (for the viewer) keeps per-tick snapshots and agent histories, detail
  events, the trust ledger, the itemized resource ledger, and community and organization
  histories. That's about 26 KB per tick, 7 KB of it the ledger (about 200 flows a tick).
- **`summary` recording** (for batch experiments) keeps metrics every 5 ticks, notable events,
  agent lifetimes, each agent's lifetime ledger totals by category, and community records.

Identical runs are identified by config hash, seed, length, code version and interventions,
and reused rather than recomputed. Any summary run can be recomputed at full detail, and it is
the same world.

## Interventions and branches

An **intervention** changes a running world from outside, at the start of a tick
(`backend/graphsim/interventions.py`). It is data, e.g. `{tick = 1000, kind = "remove_agent",
target = "top_broker"}`:

| Group | Kinds |
|---|---|
| Shocks | `remove_agent`, `start_drought` (for `length` ticks), `end_drought` |
| Economy | `give` (coin or a good; negative takes), `subsidize` (an occupation, coin per tick, for ticks), `set` (any setting, e.g. `trade.broker_commission`, checked like the file) |
| Geography | `add_road`, `remove_road` (merchants' reach follows the roads), `add_site`, `remove_site` |
| Social | `link`, `sever`, `set_trust`, `found_org` |
| Control | `reseed`: the same world with a fresh random stream |

Targets are node ids, or rules resolved at that tick (agent ids and names differ between
seeds): `top_broker`, `richest`, `poorest`, `most_connected`, `starving` (everyone starving),
`occupation:<name>`, `town:<name>`, `site:<name>`, `strongest_tie_of:<target>`. Every
intervention logs an `intervention` event that what it directly causes cites (a removed agent's
`left`, a drought it starts), and the coin and goods it moves are ledger flows (`intervention`,
`subsidy`), so the ledger stays complete. With nothing scheduled the step does nothing, and
runs are identical to runs made before interventions existed.

A **branch** is an alternate history of a stored run (`runner.branch`): the same world up to
tick T, then with interventions. Runs are deterministic, so a branch doesn't load saved state;
it replays its parent (with every earlier intervention in its history), checks the replay
against what the parent stored, and runs on. It refuses parents made by other code or settings.
A branch stores only its own ticks; `storage.lineage` says which run holds which ticks, and
every reader of tick-indexed data (metrics, snapshots, events and their causes, histories,
ledgers) reads through it, so a branch reads like a whole run and why-trails cross the branch
point. Branches of branches work the same way. A branch's measures describe its own part: from
T to the end.

**Experiments that intervene** (`branch_at`, `controls`, `arms`) branch every run at the same
tick, once per control and once per arm:

- `none`: continue unchanged. Every arm is compared with it, seed by seed.
- `reseed`: the same world, a fresh random stream. The simulation is chaotic: any nudge makes a
  run diverge, so an arm's difference from `none` mixes its real effect with chance. `reseed`
  measures chance alone. The report gives, per measure, the median size of `reseed`'s difference
  (the noise floor) and the share of seeds where the arm moved the measure further, **"beyond
  chance"**. With no real effect that share is about 50% (the noise floor is a median); a clear
  effect pushes it towards 100%.

## Measures and phenomena

`backend/graphsim/analysis.py` defines one number per run for each question: brokerage ratio,
community lifespan and turnover, drought ratios, Gini, trust, and so on. These are computed from
every tick while the run is computed, and can be recomputed later from storage with
`--reanalyze`. `[phenomena.*]` in the scenario turns a measure into a present/absent verdict.

## What the 100-seed ablation study found

`python -m graphsim.experiment ablations`: seeds 1–100 × 9 variants × 2000 ticks (900 runs,
about 21 minutes on 22 cores). "Paired" means compared with the baseline run of the same seed.

| Phenomenon (measure) | Baseline | What removes or changes it |
|---|---|---|
| **Brokerage** (broker share ÷ broker population share ≥ 2) | 100/100 worlds, median 7.7× | **Gone** without merchants, at either population (0/100), or with random partners (0/100). **Weakened** without droughts (77/100; lower in 96% of seeds). **Stronger** with a static social graph or without orgs (higher in 75–79% of seeds). |
| **Inequality** (final Gini ≥ 0.4) | 100/100, median 0.60 | **Gone** without merchants: 3/100, and 8/100 at equal population (median 0.29). So it is brokerage, not the smaller population. Random partners reduce it (84/100; lower in 97% of seeds). |
| **Drought shock** (starvation ratio ≥ 2) | 100/100, median 5.7× | Gone without droughts, as it should be. **Without merchants: gone (0/100, median 0.90), but only partly at equal population** (86/100, median 2.2×; lower than baseline in every seed). See below. |
| **Drought solidarity** (gifts in droughts ≥ 3×) | 100/100, median 18× | Requires droughts and gifting (by construction). **Weakened** without merchants (median 3.2×, barely above the threshold, so 83/100; 9.8× at equal population), with random partners (10.7×) and with a static social graph (12×). |
| **Factions** (mean communities ≥ 2) | 100/100 | 100/100 in every variant. This measure only counts groups, and at this scale there are always at least two. |
| **Factions beyond geography** (mean town alignment ≤ 0.95) | 86/100, median 0.88 | **Gone** without merchants at either population: alignment is exactly 1.0 in all 200 worlds, so every community is exactly one town's people. Merchants are what tie people across towns. **Stronger** without gifting (100/100, median 0.76; lower in 93% of seeds): gifts bind neighbours within a town. |

**Town alignment** is the normalized mutual information between the community partition and the
home-town partition, averaged over the second half of the run: 1 when communities are exactly
the towns, 0 when knowing someone's community says nothing about their town. The 0.95 threshold
was set from 20 calibration worlds (baseline median 0.885; no_merchants 1.0 in all 20) before
this study ran.

**Drought shock without merchants.** The earlier study could not tell whether brokers matter or
whether no_merchants simply has four fewer people. `no_merchants_equal_population` gives those
four slots to farmers and miners. With them, droughts cause starvation again (2.2×), but far less
than with brokers (5.7×). So population explains part of the effect, and brokerage still more
than halves the drought shock. The ledger has not yet been used to show *why* (for example,
whether brokered supply lines fail all at once in a drought); that is a question for the
viewer's attribution panel.

Other results:

- **Droughts build the social structure.** Communities formed mid-run live a median of 78 ticks
  at baseline, but only about 6 without droughts (mostly flicker). Average trust is 0.89 at
  baseline, 0.66 without gifting and 0.59 without droughts. Trust is high *because* hard times
  produce gifts.
- **Without merchants, communities are short-lived** (median 5–6 ticks). They are the towns,
  re-detected with small changes, not new groups.
- **Null result: introductions (triadic closure)** make no measurable difference to any
  phenomenon at this scale. Town alignment moves by +0.02, in 59% of seeds.
- **Null result: organizations** change nothing except brokerage (slightly stronger without
  them).

> **Measurement change since the first study.** The first study's measures were computed from
> metrics sampled every 5 ticks. They are now computed from every tick. Behaviour is identical:
> gift, departure and split counts and final Gini match exactly for the same seed. Time averages
> barely moved, but the drought ratios rose (baseline starvation 4.7× → 5.7×, gifts 13× → 18×).
> Droughts start on multiples of 200, so the 5-tick samples always caught each drought's first
> tick, before hunger had built up. One verdict changed: solidarity without merchants went from
> 0/100 to 83/100, because its median (3.2×) is right at the threshold of 3.

## What the scenario study found

`python -m graphsim.experiment topologies`: 6 worlds × seeds 1–50 × 2000 ticks (300 runs).
`python -m graphsim.experiment bridges`: `two_regions` with 1–4 bridges × both merchant placements
× seeds 1–30 (240 jobs; 150 distinct runs, because with two towns per region, 2+ bridges touch
every town, so both placements give the same map). Worlds are compared by their distributions:
medians below, with the interquartile range in brackets. Every generated world has the same
people and site capacity; `merchant_economy` has 8 merchants instead of 4.

| World | Brokers' share of trade paths | Final Gini | Social groups | Drought starvation ratio | Community lifespan (ticks) |
|---|---|---|---|---|---|
| hub_and_spokes | **0.84** [0.82, 0.87] | **0.79** [0.73, 0.82] | 1.44 | 6.2 [5.9, 6.8] | **120** [86, 160] |
| two_regions | 0.80 [0.73, 0.86] | 0.75 [0.70, 0.82] | 1.51 | 5.5 [5.2, 6.1] | 81 [64, 95] |
| resource_imbalance | 0.74 [0.58, 0.86] | 0.65 [0.58, 0.74] | 1.20 | 5.1 [4.5, 5.8] | 69 [51, 90] |
| three_towns | 0.57 [0.46, 0.71] | 0.61 [0.58, 0.64] | 1.28 | 5.8 [5.6, 6.4] | 75 [49, 117] |
| isolated_villages | 0.55 [0.44, 0.66] | 0.65 [0.56, 0.73] | 1.12 | 6.1 [5.5, 7.0] | **21** [14, 38] |
| merchant_economy | **0.46** [0.33, 0.60] | **0.54** [0.46, 0.57] | 1.22 | **4.6** [4.4, 4.9] | 46 [25, 82] |

**Every phenomenon appears in every world** (each in at least 74% of seeds, most in 100%). The
shape of the world changes how strong they are, not whether they happen.

1. **Does brokerage depend on topology? Yes, strongly.** Where every route between producers runs
   through a few merchants (all merchants in the hub; merchants at the one bridge), brokers hold
   80–84% of trade paths, against 55–57% in the line of three towns or the village chain. The
   interquartile ranges don't overlap. With twice the merchants (`merchant_economy`), brokers as
   a group hold *less* (46%): they compete. (Its `brokerage` phenomenon drops to 74% of seeds,
   partly by construction, since the measure divides by the brokers' share of the population.)
2. **Does inequality appear everywhere? Yes (Gini ≥ 0.4 in 84–100% of seeds).** It is highest
   where brokerage is concentrated (hub 0.79, two regions 0.75) and lowest with more, competing
   merchants (0.54). Inequality follows brokerage.
3. **Which networks survive drought?** None escapes the drought shock (100% of seeds in every
   world). It is mildest with more merchants (4.6×) and worst in the hub and the village chain
   (6.1–6.2×). The lowest population reached differs little (67–70% of the founding people).
   In `two_regions`, merchants spread over every town instead of the bridge towns cut the shock
   from 5.5× to 3.7× (bridges: 1).
4. **When does fragmentation occur?** Not where expected. More bridges between two regions do
   **not** knit the social graph together: with merchants in every town, separate social groups
   go from 1.6 (1 bridge) to 1.9–2.0 (3–4 bridges), and communities come to mirror towns more
   (town alignment 0.89 → 0.95). The village chain, the most spread-out map, is the *least*
   fragmented socially (1.1 groups): merchants in every other village link neighbours through
   trade friendships. What more bridges do reduce is inequality (Gini 0.78 → 0.53 from 1 to 4
   bridges). The bridge sweep's brokerage is bimodal once merchants sit in every town: in some
   seeds brokers end up with almost no trade paths (p5 of the brokerage ratio is 0).
5. **Which structures encourage strong communities?** Measured by how long communities last, the
   hub (median 120 ticks), and two regions (81). Communities in the village chain are short-lived
   (21 ticks, half of them flicker), partly because villages of 3–6 people are at or below the
   minimum community size (4), so detected groups must span villages and keep re-forming.

Other results:

- **Resources split between regions change little.** `resource_imbalance` against
  `two_regions` (same roads, same merchants): slightly less brokerage and inequality, a slightly
  milder drought, all within each other's interquartile ranges.
- **Gifting in the village chain is constant, not a drought response.** It has the most gifts
  (1,062 per 1,000 ticks) but the smallest surge in droughts (9.9×, against 17–19× elsewhere).
- **Caveat: where merchants live is a modelling choice.** It moved the results as much as the
  roads did (bridges: 1, brokers' share 0.81 at the bridge towns against 0.55 in every town).
  `generators.place_merchants_two_regions` is where to try other rules.

## What the intervention study found

Each experiment branches every run at the same tick into `none`, `reseed` and one or more arms
(50 seeds, 2000 ticks; measures cover the branch's part, from the branch tick on). "Beyond
chance" is the share of seeds where the arm moved a measure further than `reseed` typically
does: about 50% means no effect, near 100% a clear one.

- **Removing the top broker (`remove_broker`, tick 1000, three_towns and hub_and_spokes): no
  lasting effect.** Every measure stays within chance (beyond chance in 48–58% of seeds);
  brokerage, inequality, drought shock and solidarity all look as if nothing happened. In the
  viewer, another merchant becomes the top broker within the same tick. Brokerage is a
  position in the network, not a person: whoever sits there takes the role.
- **A second bridge built late (`late_bridge`, two_regions with merchants in every town,
  tick 1000): no detectable effect.** Against `none`, every measure is within chance (beyond
  chance in 30–54%). The late-bridge worlds' final Gini (median 0.69) lies between one bridge
  (0.79) and two bridges from the start (0.67), but seeds vary too much for 50 of them to tell
  whether history matters here. As a check, "building" the bridge in the world that already
  has it changes nothing: those runs equal `none` exactly, in every seed.
- **One-off food relief (`drought_relief`, 10 food to everyone starving 20 ticks into the
  tick-1000 drought): no clear effect.** In 13 of 50 seeds nobody was starving at that moment,
  so the relief was skipped and those runs equal `none` (this pulls the report's median
  differences to 0; read the per-seed numbers). In the 37 seeds where 1–3 agents were fed,
  the drought starvation ratio is slightly lower (median −0.43, beyond chance in 65% of seeds)
  and nothing else moves beyond chance. A hint at most: a small, one-off change, measured over
  980 ticks that include four more droughts.

Taken together: this economy absorbs single shocks. What changes outcomes is structure (who
can reach whom, how many merchants, droughts at all: see the ablation and scenario studies),
not removing one person or feeding a few once.

Caveat for future experiments: an intervention whose target doesn't exist at its tick is
skipped (and logged as skipped). An arm whose target is often missing looks like a smaller
effect than it is. Check the `intervention` events of the arm's runs.
