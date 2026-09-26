# graph-simulator

A simulation whose world *is* an evolving graph. Agents, towns, work sites and organizations
are nodes; friendship, trade, membership and access are edge layers. Agents change
relationships, relationships change behaviour, and structure emerges.

It is built for investigation:
- every factor lives in one file;
- every run is stored and replayable;
- mechanisms can be switched off one at a time and compared across many seeds;
- every event records what led to it.

The model and the findings so far are in [docs/spec.md](docs/spec.md).

## Quick start

You need [uv](https://docs.astral.sh/uv/) and Node 20+.

```bash
# terminal 1: the API (http://localhost:8000)
cd backend
uv run uvicorn graphsim.server:app --port 8000

# terminal 2: the viewer (http://localhost:5173)
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 and press **New run…**.

## The settings: `scenario.toml` and `scenarios/`

Everything the simulation uses is in [`scenario.toml`](scenario.toml), with a comment on every
value:

- **Economy.** Goods, site kinds and occupations. Add a good, a kind of site or an occupation
  here and the rules use it; no code changes.
- **`[layout]`.** The people and site capacity every generated world spreads over its map.
- **Behaviour.** Every parameter, grouped by topic.
- **`[mechanisms]`.** Switch whole behaviours on and off.
- **`[variants.*]`.** Named overrides (e.g. `no_gifting`), deep-merged over everything above.
- **`[experiments.*]`.** Seeds × variants, with optional parameter sweeps.
- **`[phenomena.*]`.** When a run counts as showing a phenomenon.
- **`[recording.*]`** and **`[viewer]`.** What gets stored, and what the timeline shows.

The world it runs in is a file in [`scenarios/`](scenarios): towns (with a map position, sites
and founding people) and roads, either written out town by town or made by a generator from a
few parameters:

| World | What it is |
|---|---|
| `three_towns` | The default: a farming, a mixed and a mining town in a line. |
| `hub_and_spokes` | A market town joined to outlying farming and mining towns. |
| `two_regions` | Two regions joined by `bridges` roads; merchants at the bridges or in every town. |
| `isolated_villages` | Eight small villages in a chain, each with one small farm or mine. |
| `resource_imbalance` | Two regions; one has all the farms, the other all the mines. |
| `merchant_economy` | Three towns with twice the merchants (same population). |

Generated worlds all have the same people and site capacity, so they differ only in shape;
`uv run python -m graphsim.scenarios` (in backend/) prints each world's totals and shape.
Adding a world is adding a file.

Loading is strict: a typo'd or missing key is an error naming its place.

## Experiments

```bash
cd backend
uv run python -m graphsim.experiment ablations               # 100 seeds × 9 variants
uv run python -m graphsim.experiment ablations --seeds 1-10  # a quick look
uv run python -m graphsim.experiment ablations --report      # print the report again
uv run python -m graphsim.experiment ablations --reanalyze   # after editing analysis.py
uv run python -m graphsim.experiment topologies              # 6 worlds × 50 seeds
uv run python -m graphsim.experiment bridges                 # bridges 1-4 × merchant placement
uv run python -m graphsim.experiment remove_broker           # interventions: see below
uv run python -m graphsim.experiment late_bridge
uv run python -m graphsim.experiment drought_relief
```

An experiment with `branch_at` intervenes: each run is branched at that tick once per control
(`none`, `reseed`) and per arm (named interventions, see `docs/spec.md`), and each arm is
compared with `none` seed by seed, next to how far `reseed` (chance alone) moves the same
measures.

Runs execute in parallel, and identical runs are reused, so an interrupted experiment resumes.

`--reanalyze` recomputes measures from what summary runs stored: metrics every 5 ticks. That is
fine for most measures, but it biases the drought ratios by about 20%. To be exact, re-run the
experiment instead.

The report shows, for each phenomenon and variant:
- how many worlds show it, with a 95% interval;
- the distribution of its measure;
- the change from the baseline **for the same seed**.

The same data is written to `runs/experiments/<name>/*.csv` and shown in the viewer's
**Experiments** tab, where clicking a dot opens that exact world.

One run from the command line:

```bash
uv run python -m graphsim.cli --seed 4 --variant no_gifting --set trade.gift_amount=3
uv run python -m graphsim.cli --scenario two_regions --set generator.bridges=3
```

## The viewer

- **Explore.**
  - **Run bar.** Pick a stored run, compare it with a second one side by side, or start a new
    run with any seed, variant and mechanism switches. The dialog starts from the current run's
    seed, so "same world, one change" is two clicks.
  - **Playback.** Play, step or scrub. Runs can be watched while they are still computing.
  - **Timeline.** The key metrics over the whole run, with drought bands. Click or drag to move
    both graphs to that tick; the compared run is drawn dashed.
  - **Graph controls.**
    - *Colour by* community, occupation or town, or on a scale by wealth, mean trust,
      betweenness or degree. The legend shows the range at the current tick.
    - *Highlight events* flashes trades, gifts, starvation, trust crossings, organization
      changes and arrivals and departures as playback passes them.
    - *Outlines* draws a shaded hull around each community.
  - **Inspector.** Click a node to see its state, charts of its whole life (milestones
    marked), its relationships and its history. Click its trust chart to list the trust changes
    behind a jump.
    - **Ego view** shows only that agent and its neighbours within 1 or 2 hops.
    - **Where did it come from?** splits an agent's coin and goods into their sources over its
      whole life or a window around the cursor: sales, commissions, gifts, the town levy,
      harvests and so on. It also lists top counterparties, with a *why?* link on each trade.
  - **Why?** Opens the causal trail of any event: the events that led to it, and so on
    backwards.
  - **Communities.** Every community's lifespan, with splits and mergers. Click one to
    highlight its members and open its page, which shows its size, internal trust, density and
    trade over time, who joined and left, and its key events. Organizations have the same page
    (click an organization node, then *Open page*).
  - **Intervene.** Pause where history should split and press *Intervene*: pick changes
    (remove an agent, give coin or food, subsidize an occupation, change a setting, build or
    close a road or a site, create or cut a tie, set trust, found an organization, start or end
    a drought), queue as many as you like, and *Branch*. The branch is a new run, identical up
    to that tick, and opens next to the original.
  - **Branches.** A run's family tree: what it branched from, its branches and how each ended
    compared with it. Branch points are marked on the scrubber and on the timeline.
- **Scenarios.** Every world as a card: its map (towns sized by population, with their mix of
  occupations; sites; roads), totals and generator parameters, with buttons to start a run there
  or open its latest run. Above the cards, a worlds × phenomena grid from the `topologies`
  experiment.
- **Experiments.** Results of each experiment, as described above.
- **Export.** Every chart, the whole timeline, the graph and each experiment plot has an
  *Export* menu:
  - SVG (vector, for papers), PNG at 2× or 4×, and CSV of the numbers plotted;
  - in compare mode the graph export holds both graphs side by side.

  File names say what the file shows, e.g. `run838_three_towns_seed4_baseline_t300_graph.svg`.
  Each figure embeds a caption and a `<desc>` with the run, world, seed, variant, tick, code
  version and config hash, so it can always be traced back to its data.

## Working with the data

All runs live in `runs/graphsim.db` (SQLite). The tables are described at the top of
[`backend/graphsim/storage.py`](backend/graphsim/storage.py).

No virtual environment needs activating: `uv run` uses (and if needed creates) `backend/.venv`.
From the repository root, point it at the backend with `--project backend`; from `backend/`,
leave that out.

```bash
uv run --project backend python -m graphsim.query runs                  # the newest runs
uv run --project backend python -m graphsim.query show 1740             # settings, phenomena, measures
uv run --project backend python -m graphsim.query metrics 1740 gini_coin starving --every 100
uv run --project backend python -m graphsim.query events 1740 --kind new_top_broker
uv run --project backend python -m graphsim.query agent 1740 agent-004  # life, coin sources, history
uv run --project backend python -m graphsim.query sql "select name, value from run_measures where run_id = 1740"
uv run --project backend python -m graphsim.query --csv gini.csv metrics 1740 gini_coin
```

A branch reads like a complete run: its parent's history fills in the ticks before it.

For pandas (not a dependency), `--with` adds it for one session:

```bash
uv run --project backend --with pandas python
```

```python
import sqlite3, pandas as pd
db = sqlite3.connect("runs/graphsim.db")
m = pd.read_sql("select tick, name, value from tick_metrics where run_id = 1740", db)
m.pivot(index="tick", columns="name", values="value")[["gini_coin", "starving"]].describe()
```

Any SQLite browser (e.g. DB Browser for SQLite) can open the file too.

## Layout

```
scenario.toml                  every factor of the model
scenarios/                     the worlds it runs in (one file each)
docs/spec.md                   the model, in prose, and what experiments found
backend/graphsim/
  config.py                    the settings files' schema and strict loader
  generators.py  scenarios.py  generated worlds; every world's totals side by side
  model.py  world_gen.py       the world (multiplex edges keyed by (a, b, layer))
  engine.py                    step(): the tick order, readable top to bottom
  rules/                       needs, production, trade, market, relationships, groups
  events.py                    the event log with causal links
  communities.py               community identity over time
  metrics.py                   network measurements and structural events
  milestones.py                became wealthy / poor / a hub, explained from the ledger
  recorder.py  storage.py      what gets stored, and the run database
  runner.py                    compute (or reuse) a run
  analysis.py  report.py       run-level measures; experiment statistics
  experiment.py  cli.py        command-line entry points
  server.py                    the viewer's API
frontend/src/                  React + Cytoscape viewer (charts are plain SVG)
```

## Tests and checks

```bash
cd backend && uv run pytest && uv run ruff check . && uv run ruff format --check .
cd frontend && npm run typecheck && npm run build
```

The tests cover determinism across processes, each mechanism switch, causal links, community
lineage, resource conservation (the ledger accounts for every coin and good), milestones,
generated worlds (same totals, deterministic maps), storage round-trips, the experiment runner,
the report statistics and the API.
