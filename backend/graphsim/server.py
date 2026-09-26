"""The viewer's API: browse stored runs, start new ones, and dig into any tick.

Run from backend/:   uv run uvicorn graphsim.server:app --port 8000

Runs are computed in background threads and written to the run database as they go, so the
viewer can start playing a run while it is still being computed. Everything the viewer shows
comes from the database (see storage.py); nothing here simulates on its own.
"""

import sqlite3
import threading
from collections.abc import Iterator
from dataclasses import asdict
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel

from graphsim import analysis, interventions, report, runner, storage
from graphsim.communities import entity_id
from graphsim.config import PARTNER_CHOICE, SOCIAL_DYNAMICS, ScenarioError, load_scenario
from graphsim.scenarios import world_summary

app = FastAPI(title="graphsim")
DATABASE = load_scenario().database


def db() -> Iterator[sqlite3.Connection]:
    conn = storage.connect(DATABASE)
    try:
        yield conn
    finally:
        conn.close()


Db = Annotated[sqlite3.Connection, Depends(db)]  # a database connection for one request


# --- scenario ---------------------------------------------------------------------------------


@app.get("/api/scenario")
def scenario_info() -> dict[str, Any]:
    """Everything the viewer needs to know about scenario.toml."""
    scenario = load_scenario()
    cfg = scenario.config()
    return {
        "name": scenario.name,
        "default_scenario": scenario.default_scenario,
        "seed": scenario.seed,
        "ticks": scenario.ticks,
        "goods": {name: asdict(spec) for name, spec in cfg.goods.items()},
        "occupations": {name: asdict(spec) for name, spec in cfg.occupations.items()},
        "mechanisms": asdict(cfg.mechanisms),
        "mechanism_choices": {
            "social_dynamics": SOCIAL_DYNAMICS,
            "partner_choice": PARTNER_CHOICE,
        },
        "variants": {
            name: variant.get("description", "") for name, variant in scenario.variants.items()
        },
        "experiments": {
            name: {
                "description": spec.description,
                "seeds": len(spec.seeds),
                "scenarios": spec.scenarios,
                "variants": spec.variants,
                "ticks": spec.ticks,
            }
            for name, spec in scenario.experiments.items()
        },
        "phenomena": {name: asdict(spec) for name, spec in scenario.phenomena.items()},
        "timeline": scenario.viewer.get("timeline", []),
    }


@app.get("/api/scenarios")
def scenarios() -> list[dict[str, Any]]:
    """Every world in scenarios/: what it is, its map (as built, for generated ones), its
    totals and shape, and which variants can run on it."""
    scenario = load_scenario()
    result = []
    for name, spec in scenario.scenarios.items():
        cfg = scenario.config(scenario=name)
        result.append(
            {
                "name": name,
                "title": spec.title,
                "description": spec.description,
                "generator": spec.generator,
                "towns": [
                    {
                        "name": town_name,
                        "position": list(town.position),
                        "sites": [asdict(site) for site in town.sites],
                        "founding": town.founding,
                    }
                    for town_name, town in cfg.world.towns.items()
                ],
                "roads": [{"from": road.from_, "to": road.to} for road in cfg.world.roads],
                "summary": world_summary(cfg),
                "variants": [v for v in scenario.variants if _runs_on(scenario, v, name)],
            }
        )
    default = scenario.default_scenario
    return sorted(result, key=lambda s: (s["name"] != default, s["name"]))


def _runs_on(scenario, variant: str, world: str) -> bool:
    try:
        scenario.config(variant, scenario=world)
    except ScenarioError:
        return False  # e.g. a variant that names another map's towns
    return True


# --- runs -------------------------------------------------------------------------------------


class NewRun(BaseModel):
    seed: int
    ticks: int
    scenario: str | None = None  # a world in scenarios/; default: scenario.toml [run] scenario
    variant: str = "baseline"
    overrides: dict[str, Any] = {}  # may include generator.<param> for generated worlds
    label: str = ""


@app.get("/api/runs")
def list_runs(conn: Db, experiment: str | None = None) -> list[dict[str, Any]]:
    return storage.list_runs(conn, experiment)


@app.post("/api/runs")
def start_run(conn: Db, request: NewRun) -> dict[str, Any]:
    """Starts computing a full-detail run (or returns an identical stored one)."""
    scenario = load_scenario()
    try:
        run_id, done = runner.prepare(
            conn,
            scenario,
            seed=request.seed,
            ticks=request.ticks,
            variant=request.variant,
            overrides=request.overrides,
            level="full",
            label=request.label,
            scenario_name=request.scenario,
        )
    except ScenarioError as error:
        raise HTTPException(400, str(error)) from error
    if not done:
        _compute_in_background(run_id)
    return storage.get_run(conn, run_id) or {}


@app.get("/api/runs/{run_id}")
def get_run(conn: Db, run_id: int) -> dict[str, Any]:
    return _require_run(conn, run_id)


class NewBranch(BaseModel):
    tick: int
    interventions: list[dict[str, Any]] = []  # applied at `tick`; e.g. {"kind": "reseed"}
    label: str = ""


@app.post("/api/runs/{run_id}/branches")
def start_branch(conn: Db, run_id: int, request: NewBranch) -> dict[str, Any]:
    """Starts computing an alternate history of the run from `tick` (or returns an identical
    stored one). Before `tick` it is the run itself; see runner.branch."""
    _require_run(conn, run_id)
    try:
        branch_id, done = runner.prepare_branch(
            conn, load_scenario(), run_id, request.tick, request.interventions, request.label
        )
    except (ValueError, ScenarioError) as error:  # includes interventions.InterventionError
        raise HTTPException(400, str(error)) from error
    if not done:
        _compute_in_background(branch_id)
    return storage.get_run(conn, branch_id) or {}


@app.get("/api/runs/{run_id}/lineage")
def lineage(conn: Db, run_id: int) -> dict[str, Any]:
    """The run's family: the runs it branched from (oldest first), its siblings (other branches
    of its parent) and its own branches, each with its numbers at its last stored tick."""
    run = _require_run(conn, run_id)
    ancestors = [storage.get_run(conn, r) for r, _, _ in storage.lineage(conn, run_id)[:-1]]

    def children(parent: int) -> list[dict[str, Any]]:
        rows = conn.execute("select id from runs where parent_run = ? order by id", (parent,))
        return [storage.get_run(conn, row["id"]) for row in rows]

    def with_final(info: dict[str, Any]) -> dict[str, Any]:
        return {**info, "final": storage.final_metrics(conn, info["id"], FINAL_METRICS)}

    siblings = (
        [r for r in children(run["parent_run"]) if r["id"] != run_id] if run["parent_run"] else []
    )
    return {
        "run": with_final(run),
        "ancestors": [with_final(r) for r in ancestors if r],
        "siblings": [with_final(r) for r in siblings],
        "children": [with_final(r) for r in children(run_id)],
        "intervention_kinds": {kind: list(params) for kind, params in interventions.KINDS.items()},
    }


# Numbers shown to compare a run with its branches (their values at the last stored tick).
FINAL_METRICS = ["population", "gini_coin", "broker_share", "avg_trust", "starving"]


@app.post("/api/runs/{run_id}/materialize")
def materialize(conn: Db, run_id: int) -> dict[str, Any]:
    """A full-detail version of a summary run (e.g. from an experiment), computed if needed."""
    info = _require_run(conn, run_id)
    if info["level"] == "full":
        return info
    scenario = load_scenario()
    try:
        settings = scenario.config(info["variant"], info["overrides"], scenario=info["scenario"])
        if settings.config_hash() != info["config_hash"]:
            raise HTTPException(409, "the scenario files have changed since this run was made")
        full_id, done = runner.prepare(
            conn,
            scenario,
            seed=info["seed"],
            ticks=info["ticks"],
            variant=info["variant"],
            overrides=info["overrides"],
            level="full",
            experiment=info["experiment"],
            label=info["label"],
            scenario_name=info["scenario"],
        )
    except ScenarioError as error:
        raise HTTPException(400, str(error)) from error
    if not done:
        _compute_in_background(full_id)
    return storage.get_run(conn, full_id) or {}


# --- one run's data ---------------------------------------------------------------------------


@app.get("/api/runs/{run_id}/metrics")
def metrics(conn: Db, run_id: int, names: str = "") -> dict[str, Any]:
    wanted = [n for n in names.split(",") if n] or None
    return {
        "names": storage.metric_names(conn, run_id),
        "series": storage.metric_series(conn, run_id, wanted),
    }


@app.get("/api/runs/{run_id}/snapshots")
def snapshots(conn: Db, run_id: int, first: int = 0, count: int = 1) -> list[dict]:
    return storage.snapshots(conn, run_id, first, min(count, 200))


@app.get("/api/runs/{run_id}/events")
def events(
    conn: Db,
    run_id: int,
    first: int = 0,
    last: int | None = None,
    entity: str | None = None,
    detail: bool = False,
    kinds: str = "",
    limit: int = 500,
) -> list[dict[str, Any]]:
    kind_list = [k for k in kinds.split(",") if k] or None
    return storage.events(conn, run_id, first, last, entity, detail, kind_list, min(limit, 5000))


@app.get("/api/runs/{run_id}/events/{event_id}/trail")
def trail(conn: Db, run_id: int, event_id: int, depth: int = 3) -> dict[str, Any]:
    result = storage.causal_trail(conn, run_id, event_id, min(depth, 8))
    if result is None:
        raise HTTPException(404, f"run {run_id} has no event {event_id}")
    return result


@app.get("/api/runs/{run_id}/agents")
def agents(conn: Db, run_id: int) -> list[dict[str, Any]]:
    return storage.agents(conn, run_id)


@app.get("/api/runs/{run_id}/agents/{agent_id}/history")
def agent_history(conn: Db, run_id: int, agent_id: str) -> dict[str, Any]:
    lifetime = next((a for a in storage.agents(conn, run_id) if a["agent_id"] == agent_id), None)
    return {"lifetime": lifetime, "ticks": storage.agent_history(conn, run_id, agent_id)}


@app.get("/api/runs/{run_id}/trust")
def trust(
    conn: Db,
    run_id: int,
    agent: str,
    other: str | None = None,
    first: int = 0,
    last: int | None = None,
) -> list[dict[str, Any]]:
    """Trust-ledger entries for an agent's ties, each with the event that caused it."""
    changes = storage.trust_changes(conn, run_id, agent, other, first, last)
    return [{**c, "event": storage.event(conn, run_id, c["event_id"])} for c in changes]


@app.get("/api/runs/{run_id}/agents/{agent_id}/flows")
def agent_flows(
    conn: Db, run_id: int, agent_id: str, first: int = 0, last: int | None = None
) -> dict[str, Any]:
    """Where the agent's coin and goods came from and went, between two ticks: every ledger
    entry (full-level runs), a summary by category and counterparty, and lifetime totals."""
    entries = storage.flows(conn, run_id, agent_id, first, last)
    return {
        "flows": entries,
        **analysis.ledger_summary(entries),
        "lifetime": storage.agent_totals(conn, run_id, agent_id),
    }


@app.get("/api/runs/{run_id}/communities")
def communities(conn: Db, run_id: int) -> dict[str, Any]:
    return {
        "communities": storage.communities(conn, run_id),
        "sizes": storage.community_sizes(conn, run_id),
    }


@app.get("/api/runs/{run_id}/communities/{community_id:int}")
def community(conn: Db, run_id: int, community_id: int) -> dict[str, Any]:
    """One community's life: its record, its size and internal ties at every detection, who
    joined and left between detections, and its events."""
    record = next(
        (c for c in storage.communities(conn, run_id) if c["community_id"] == community_id), None
    )
    if record is None:
        raise HTTPException(404, f"run {run_id} has no community {community_id}")
    history = storage.community_history(conn, run_id, community_id)
    return {
        "record": record,
        "history": [{k: v for k, v in row.items() if k != "members"} for row in history],
        "changes": _membership_changes(history),
        "events": storage.events(conn, run_id, entity=entity_id(community_id), limit=2000),
    }


@app.get("/api/runs/{run_id}/orgs/{org_id}")
def organization(conn: Db, run_id: int, org_id: str) -> dict[str, Any]:
    history = storage.org_history(conn, run_id, org_id)
    return {
        "name": history[0]["name"] if history else org_id,
        "history": [{k: v for k, v in row.items() if k != "members"} for row in history],
        "changes": _membership_changes(history),
        "events": storage.events(conn, run_id, entity=org_id, limit=2000),
    }


@app.get("/api/runs/{run_id}/communities/members")
def community_members(conn: Db, run_id: int, tick: int) -> dict[int, list[str]]:
    return storage.community_members(conn, run_id, tick)


@app.get("/api/runs/{run_id}/measures")
def measures(conn: Db, run_id: int) -> dict[str, float]:
    return storage.measures(conn, run_id)


# --- experiments ------------------------------------------------------------------------------


@app.get("/api/experiments/{name}")
def experiment(conn: Db, name: str) -> dict[str, Any]:
    scenario = load_scenario()
    if name not in scenario.experiments:
        raise HTTPException(404, f"no experiment {name!r} in scenario.toml")
    return report.build(conn, scenario, name)


# --- helpers ----------------------------------------------------------------------------------


def _membership_changes(history: list[dict]) -> list[dict[str, Any]]:
    """Who joined and who left between consecutive records of a group."""
    changes = []
    for before, after in zip(history, history[1:], strict=False):
        joined = sorted(set(after["members"]) - set(before["members"]))
        left = sorted(set(before["members"]) - set(after["members"]))
        if joined or left:
            changes.append({"tick": after["tick"], "joined": joined, "left": left})
    return changes


def _require_run(conn, run_id: int) -> dict[str, Any]:
    info = storage.get_run(conn, run_id)
    if info is None:
        raise HTTPException(404, f"no run {run_id}")
    return info


def _compute_in_background(run_id: int) -> None:
    def work() -> None:
        conn = storage.connect(DATABASE)
        try:
            runner.execute(conn, load_scenario(), run_id)
        finally:
            conn.close()

    threading.Thread(target=work, name=f"run-{run_id}", daemon=True).start()
