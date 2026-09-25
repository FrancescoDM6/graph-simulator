# graph-simulator

A simulation whose world *is* an evolving graph. Agents, towns, work sites and organizations
are nodes. Friendship, trade, membership and access are edge layers. Nothing exists outside
the graph: agents change relationships, relationships change behaviour, and structure emerges.

The model is described in [docs/spec.md](docs/spec.md): node and edge types, the tick order,
and which emergent phenomena it produces.

## Running it

You need [uv](https://docs.astral.sh/uv/) and Node 20+.

```bash
# terminal 1: the simulation server (http://localhost:8000)
cd backend
uv run uvicorn graphsim.server:app --port 8000

# terminal 2: the viewer (http://localhost:5173)
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 and press **Play**.

- Click a node to see its state, its relationships by layer, and its full history with causes.
- Toggle layers in the top bar.
- Tick **network-level only** in the event feed to see just structural events: communities
  forming, the network splitting, a new top broker, price moves.

### Headless runs

```bash
cd backend
uv run python -m graphsim.cli --seed 1 --ticks 5000
```

This writes `runs/seed1/events.jsonl` and `runs/seed1/metrics.csv`, and prints a summary of
the four target phenomena. Use it to check a config change before looking at the UI.

### Tests and checks

```bash
cd backend && uv run pytest && uv run ruff check . && uv run ruff format --check .
cd frontend && npm run typecheck
```

## Layout

```
docs/spec.md                  the model, in prose
backend/graphsim/
  config.py                   every tunable number, one commented field each
  model.py                    World, nodes, multiplex edges keyed by (a, b, layer)
  world_gen.py                geography and founding population (TOWNS)
  engine.py                   step(): the tick order, readable top to bottom
  rules/                      one module per phase: needs, production, trade, market,
                              relationships, groups
  metrics.py                  NetworkX measurements + structural events (read-only)
  events.py                   the event log; every event carries a cause
  serialize.py / server.py    JSON snapshots over a WebSocket
  cli.py                      headless runs and the phenomena summary
frontend/src/
  types.ts                    mirror of serialize.py (change both together)
  api.ts                      WebSocket hook + history fetch
  GraphView.tsx               Cytoscape + incremental fcose layout
  graphStyle.ts               every visual encoding (size, colour, shape)
  Controls / MetricsBar / Inspector / EventFeed / Legend
```

## Tuning

1. Change a number in `backend/graphsim/config.py`.
2. Run the CLI for a few seeds.
3. Compare the phenomena summary.

The model is balanced as a whole, so change one thing at a time. Useful levers:

| Want | Try |
|------|-----|
| Harsher droughts | lower `drought_regen_factor`, raise `drought_length` |
| Stronger brokers / more inequality | raise `merchant_markup`, lower `town_levy` |
| Denser or sparser social graph | `max_social_ties`, `meet_chance`, `social_decay` |
| More organizations | lower `found_min_trust` / `join_score` |

Determinism: the same seed always gives the same history. This is enforced by a test that
runs two processes with different hash seeds. When adding code, iterate over dicts or sorted
lists, never over sets.
