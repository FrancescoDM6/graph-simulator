"""The run database: every run the simulator has computed, in one SQLite file.

Nothing is ever overwritten: re-running with different settings creates a new run, so runs can
always be compared. The schema below is the whole data model; the functions after it are the
only code that reads or writes it (used by the runner, the API and the analysis).

Many tables are "long": one row per (run, tick, thing), which is easy to query from pandas:
    pd.read_sql("select * from tick_metrics where run_id = 3", sqlite3.connect(path))
"""

import gzip
import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SCHEMA = """
create table if not exists runs (
    id integer primary key,
    created text not null,
    scenario text not null,
    variant text not null,
    overrides text not null,        -- JSON {"section.key": value}
    seed integer not null,
    ticks integer not null,
    level text not null,            -- "summary" or "full" (see scenario.toml [recording])
    config_hash text not null,
    config_json text not null,      -- the exact SimConfig used
    code_version text not null,     -- git commit, "+<hash>" if there were local changes
    experiment text not null,       -- experiment name, or "" for a one-off run
    label text not null,
    status text not null,           -- "running", "done" or "failed"
    ticks_done integer not null,
    parent_run integer,             -- a branch: the run it branched from (see runner.branch)
    branch_tick integer,            -- ... and the tick it starts at (earlier ticks: the parent's)
    interventions text not null default '[]'  -- JSON: every intervention in its history
);
create table if not exists tick_metrics (
    run_id integer, tick integer, name text, value real,
    primary key (run_id, name, tick)
) without rowid;
create table if not exists agents (
    run_id integer, agent_id text, name text, occupation text, home text,
    arrived integer, departed integer, departure_event integer, founding integer,
    primary key (run_id, agent_id)
) without rowid;
create table if not exists agent_ticks (
    run_id integer, agent_id text, tick integer,
    occupation text, org text, community integer, coin real, inventory text,
    mean_trust real, social_ties integer, trade_ties integer, betweenness real,
    bought integer, sold integer, brokered integer, gifts_given integer, gifts_received integer,
    hunger integer,
    primary key (run_id, agent_id, tick)
) without rowid;
create table if not exists events (
    run_id integer, id integer, tick integer, kind text, subjects text,
    message text, cause text, detail integer,
    primary key (run_id, id)
) without rowid;
create index if not exists events_by_tick on events (run_id, tick);
create table if not exists event_subjects (
    run_id integer, entity text, event_id integer,
    primary key (run_id, entity, event_id)
) without rowid;
create table if not exists event_causes (
    run_id integer, event_id integer, cause_id integer,
    primary key (run_id, event_id, cause_id)
) without rowid;
create index if not exists event_effects on event_causes (run_id, cause_id);
create table if not exists trust_changes (
    run_id integer, tick integer, a text, b text, before real, after real, event_id integer
);
create index if not exists trust_by_agent_a on trust_changes (run_id, a, tick);
create index if not exists trust_by_agent_b on trust_changes (run_id, b, tick);
create table if not exists communities (
    run_id integer, community_id integer, born integer, died integer, fate text,
    parent integer, merged_into integer, peak_size integer, members_ever integer,
    mean_turnover real, continuations integer,
    primary key (run_id, community_id)
) without rowid;
create table if not exists community_ticks (
    run_id integer, tick integer, community_id integer, size integer, members text,
    density real, trust real, trade real,  -- internal social density, mean trust, trade volume
    primary key (run_id, community_id, tick)
) without rowid;
create table if not exists org_ticks (      -- organizations over time (full-level runs)
    run_id integer, tick integer, org_id text, name text, size integer, members text,
    density real, trust real,
    primary key (run_id, org_id, tick)
) without rowid;
create table if not exists snapshots (
    run_id integer, tick integer, data blob,   -- gzipped JSON from serialize.snapshot
    primary key (run_id, tick)
) without rowid;
create table if not exists run_measures (
    run_id integer, name text, value real,
    primary key (run_id, name)
) without rowid;
create table if not exists flows (          -- the resource ledger (full-level runs)
    run_id integer, tick integer, agent_id text, asset text, category text, amount real,
    counterparty text, event_id integer
);
create index if not exists flows_by_agent on flows (run_id, agent_id, tick);
create table if not exists agent_totals (   -- lifetime ledger totals, kept at every level
    run_id integer, agent_id text, asset text, category text, amount real,
    primary key (run_id, agent_id, asset, category)
) without rowid;
create table if not exists experiment_runs (   -- which run answered each job of an experiment
    experiment text, label text, seed integer, run_id integer,
    primary key (experiment, label, seed)
) without rowid;
"""

LEVELS = ("summary", "full")  # a "full" run can stand in for a "summary" one, not vice versa


@dataclass
class Batch:
    """Rows produced by the recorder for a stretch of ticks, ready to insert."""

    ticks_done: int = 0
    metrics: list[tuple] = field(default_factory=list)  # (tick, name, value)
    agents: list[tuple] = field(default_factory=list)  # see the agents table
    agent_ticks: list[tuple] = field(default_factory=list)
    events: list[tuple] = field(default_factory=list)  # (id, tick, kind, subjects, ...)
    event_subjects: list[tuple] = field(default_factory=list)  # (entity, event_id)
    event_causes: list[tuple] = field(default_factory=list)  # (event_id, cause_id)
    trust_changes: list[tuple] = field(default_factory=list)
    flows: list[tuple] = field(default_factory=list)  # (tick, agent, asset, category, ...)
    community_ticks: list[tuple] = field(default_factory=list)
    org_ticks: list[tuple] = field(default_factory=list)
    snapshots: list[tuple] = field(default_factory=list)  # (tick, gzipped JSON)
    communities: list[tuple] = field(default_factory=list)  # only in the final batch
    agent_totals: list[tuple] = field(default_factory=list)  # only in the final batch
    measures: dict[str, float] = field(default_factory=dict)  # only in the final batch


_prepared: set[Path] = set()  # databases whose schema this process has already set up


def connect(path: Path | str) -> sqlite3.Connection:
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("pragma synchronous = normal")
    if path not in _prepared:
        # Setting up the schema needs a write lock, so do it once per process: otherwise every
        # reader would queue behind whoever is writing (e.g. an experiment filling the database).
        if conn.execute("pragma journal_mode").fetchone()[0] != "wal":
            conn.execute("pragma journal_mode = wal")  # readers aren't blocked by a writer
        conn.executescript(SCHEMA)
        _add_missing_columns(conn)
        _name_old_worlds(conn)
        _prepared.add(path)
    return conn


# Columns added after a table was first created: (table, column, type). Databases made by older
# versions get them added (as empty) when opened, so old runs stay readable.
ADDED_COLUMNS = [
    ("runs", "parent_run", "integer"),
    ("runs", "branch_tick", "integer"),
    ("runs", "interventions", "text not null default '[]'"),
    ("community_ticks", "density", "real"),
    ("community_ticks", "trust", "real"),
    ("community_ticks", "trade", "real"),
]


def _name_old_worlds(conn: sqlite3.Connection) -> None:
    """Runs made before scenarios/ existed stored the settings file's name ("scenario") where
    the world's name now goes; they all ran on the map now called three_towns."""
    with conn:
        conn.execute("update runs set scenario = 'three_towns' where scenario = 'scenario'")


def _add_missing_columns(conn: sqlite3.Connection) -> None:
    for table, column, kind in ADDED_COLUMNS:
        existing = {row["name"] for row in conn.execute(f"pragma table_info({table})")}
        if column not in existing:
            with conn:
                conn.execute(f"alter table {table} add column {column} {kind}")


# --- writing ----------------------------------------------------------------------------------


def create_run(conn: sqlite3.Connection, meta: dict[str, Any]) -> int:
    columns = ", ".join(meta)
    placeholders = ", ".join("?" for _ in meta)
    with conn:
        cursor = conn.execute(
            f"insert into runs ({columns}) values ({placeholders})", list(meta.values())
        )
    return int(cursor.lastrowid)


def write_batch(conn: sqlite3.Connection, run_id: int, batch: Batch) -> None:
    def insert(table: str, rows: list[tuple], replace: bool = False) -> None:
        if not rows:
            return
        verb = "insert or replace" if replace else "insert"
        placeholders = ", ".join("?" for _ in range(len(rows[0]) + 1))
        conn.executemany(
            f"{verb} into {table} values ({placeholders})", [(run_id, *row) for row in rows]
        )

    with conn:
        insert("tick_metrics", [(tick, name, value) for tick, name, value in batch.metrics])
        insert("agents", batch.agents, replace=True)
        insert("agent_ticks", batch.agent_ticks)
        insert("events", batch.events)
        insert("event_subjects", batch.event_subjects)
        insert("event_causes", batch.event_causes)
        insert("trust_changes", batch.trust_changes)
        insert("flows", batch.flows)
        insert("agent_totals", batch.agent_totals, replace=True)
        insert("community_ticks", batch.community_ticks)
        insert("org_ticks", batch.org_ticks)
        insert("snapshots", batch.snapshots)
        insert("communities", batch.communities, replace=True)
        insert("run_measures", list(batch.measures.items()), replace=True)
        conn.execute("update runs set ticks_done = ? where id = ?", (batch.ticks_done, run_id))


def assign_experiment_run(
    conn: sqlite3.Connection, experiment: str, label: str, seed: int, run_id: int
) -> None:
    with conn:
        conn.execute(
            "insert or replace into experiment_runs values (?, ?, ?, ?)",
            (experiment, label, seed, run_id),
        )


def forget_old_labels(conn: sqlite3.Connection, experiment: str, labels: list[str]) -> None:
    """Drops the experiment's assignments under labels it no longer has (after its variants or
    sweep changed in scenario.toml), so reports show only what the experiment is now. The runs
    themselves stay stored."""
    placeholders = ", ".join("?" for _ in labels)
    with conn:
        conn.execute(
            f"delete from experiment_runs where experiment = ? and label not in ({placeholders})",
            (experiment, *labels),
        )


def set_status(conn: sqlite3.Connection, run_id: int, status: str) -> None:
    with conn:
        conn.execute("update runs set status = ? where id = ?", (status, run_id))


def delete_run(conn: sqlite3.Connection, run_id: int) -> None:
    """Removes a run and all its rows (used to clean up runs that failed half-way)."""
    tables = [
        "tick_metrics", "agents", "agent_ticks", "events", "event_subjects", "event_causes",
        "trust_changes", "communities", "community_ticks", "snapshots", "run_measures",
        "flows", "agent_totals", "org_ticks",
    ]  # fmt: skip
    with conn:
        for table in tables:
            conn.execute(f"delete from {table} where run_id = ?", (run_id,))
        conn.execute("delete from experiment_runs where run_id = ?", (run_id,))
        conn.execute("delete from runs where id = ?", (run_id,))


# --- reading ----------------------------------------------------------------------------------


def find_cached_run(
    conn: sqlite3.Connection,
    config_hash: str,
    seed: int,
    ticks: int,
    level: str,
    code: str,
    interventions: str = "[]",
    branch_tick: int | None = None,
) -> int | None:
    """A finished run with exactly these settings (and interventions, from the same branch
    tick), at this level of detail or more."""
    acceptable = LEVELS[LEVELS.index(level) :]
    placeholders = ", ".join("?" for _ in acceptable)
    row = conn.execute(
        f"""select id from runs where config_hash = ? and seed = ? and ticks = ?
            and code_version = ? and status = 'done' and level in ({placeholders})
            and interventions = ? and branch_tick is ?
            order by id desc limit 1""",
        (config_hash, seed, ticks, code, *acceptable, interventions, branch_tick),
    ).fetchone()
    return row["id"] if row else None


def lineage(conn: sqlite3.Connection, run_id: int) -> list[tuple[int, int, int]]:
    """Which run holds which ticks: [(run id, first tick, last tick), ...], oldest first. An
    ordinary run holds all its ticks; a branch holds its ticks from its branch tick, and its
    parent (and so on up) the ones before."""
    segments = []
    last = 1 << 62
    while True:
        row = conn.execute(
            "select parent_run, branch_tick from runs where id = ?", (run_id,)
        ).fetchone()
        if row is None or row["parent_run"] is None:
            segments.append((run_id, 0, last))
            return segments[::-1]
        segments.append((run_id, row["branch_tick"], last))
        last = row["branch_tick"] - 1
        run_id = row["parent_run"]


def _owned(conn: sqlite3.Connection, run_id: int, alias: str = "") -> tuple[str, list[Any]]:
    """A SQL condition selecting the rows of a run's history (its own, and for a branch its
    ancestors' before the branch tick), with its parameters. For tables with a `tick` column."""
    p = f"{alias}." if alias else ""
    segments = lineage(conn, run_id)
    sql = " or ".join(f"({p}run_id = ? and {p}tick between ? and ?)" for _ in segments)
    return f"({sql})", [value for segment in segments for value in segment]


def list_runs(conn: sqlite3.Connection, experiment: str | None = None) -> list[dict[str, Any]]:
    query = """select id, created, scenario, variant, overrides, seed, ticks, level, config_hash,
                      code_version, experiment, label, status, ticks_done, parent_run,
                      branch_tick, interventions from runs"""
    params: tuple = ()
    if experiment is not None:
        query += " where experiment = ?"
        params = (experiment,)
    rows = conn.execute(query + " order by id", params).fetchall()
    return [_run_dict(row) for row in rows]


def get_run(conn: sqlite3.Connection, run_id: int) -> dict[str, Any] | None:
    row = conn.execute("select * from runs where id = ?", (run_id,)).fetchone()
    return _run_dict(row) if row else None


def metric_names(conn: sqlite3.Connection, run_id: int) -> list[str]:
    owned, params = _owned(conn, run_id)
    rows = conn.execute(
        f"select distinct name from tick_metrics where {owned} order by name", params
    ).fetchall()
    return [row["name"] for row in rows]


def metric_series(
    conn: sqlite3.Connection, run_id: int, names: list[str] | None = None
) -> dict[str, list[tuple[int, float]]]:
    """name -> [(tick, value), ...] in tick order."""
    owned, params = _owned(conn, run_id)
    query = f"select name, tick, value from tick_metrics where {owned}"
    if names:
        query += f" and name in ({', '.join('?' for _ in names)})"
        params += names
    series: dict[str, list[tuple[int, float]]] = {}
    for row in conn.execute(query + " order by name, tick", params):
        series.setdefault(row["name"], []).append((row["tick"], row["value"]))
    return series


def snapshots(conn: sqlite3.Connection, run_id: int, first: int, count: int) -> list[dict]:
    owned, params = _owned(conn, run_id)
    rows = conn.execute(
        f"select data from snapshots where {owned} and tick >= ? order by tick limit ?",
        (*params, first, count),
    ).fetchall()
    return [json.loads(gzip.decompress(row["data"])) for row in rows]


def events(
    conn: sqlite3.Connection,
    run_id: int,
    first_tick: int = 0,
    last_tick: int | None = None,
    entity: str | None = None,
    include_detail: bool = False,
    kinds: list[str] | None = None,
    limit: int = 1000,
) -> list[dict[str, Any]]:
    query = "select e.* from events e"
    owned, params = _owned(conn, run_id, "e")
    conditions = [owned, "e.tick >= ?"]
    params.append(first_tick)
    if entity:
        query += " join event_subjects s on s.run_id = e.run_id and s.event_id = e.id"
        conditions.append("s.entity = ?")
        params.append(entity)
    if last_tick is not None:
        conditions.append("e.tick <= ?")
        params.append(last_tick)
    if not include_detail:
        conditions.append("e.detail = 0")
    if kinds:
        conditions.append(f"e.kind in ({', '.join('?' for _ in kinds)})")
        params += kinds
    query += " where " + " and ".join(conditions) + " order by e.id limit ?"
    rows = conn.execute(query, [*params, limit]).fetchall()
    return [_event_dict(conn, row) for row in rows]


def event(conn: sqlite3.Connection, run_id: int, event_id: int) -> dict[str, Any] | None:
    owned, params = _owned(conn, run_id)
    row = conn.execute(f"select * from events where {owned} and id = ?", (*params, event_id))
    row = row.fetchone()
    return _event_dict(conn, row) if row else None


def causal_trail(
    conn: sqlite3.Connection, run_id: int, event_id: int, depth: int = 4
) -> dict[str, Any] | None:
    """The event with its causes nested inside it, `depth` levels back. Causes that weren't
    stored (detail events of a summary-level run) appear as {"id": ..., "missing": True}."""
    root = event(conn, run_id, event_id)
    if root is None:
        return None

    def expand(node: dict[str, Any], remaining: int) -> dict[str, Any]:
        causes = []
        for cause_id in node["caused_by"]:
            cause = event(conn, run_id, cause_id)
            if cause is None:
                causes.append({"id": cause_id, "missing": True})
            elif remaining > 1:
                causes.append(expand(cause, remaining - 1))
            else:
                causes.append({**cause, "causes": None})  # None = not expanded yet
        return {**node, "causes": causes}

    return expand(root, depth)


def agents(conn: sqlite3.Connection, run_id: int) -> list[dict[str, Any]]:
    rows = conn.execute("select * from agents where run_id = ? order by agent_id", (run_id,))
    return [_without_run(row) for row in rows]


def agent_history(conn: sqlite3.Connection, run_id: int, agent_id: str) -> list[dict[str, Any]]:
    owned, params = _owned(conn, run_id)
    rows = conn.execute(
        f"select * from agent_ticks where {owned} and agent_id = ? order by tick",
        (*params, agent_id),
    ).fetchall()
    return [_without_run(row) | {"inventory": json.loads(row["inventory"])} for row in rows]


def trust_changes(
    conn: sqlite3.Connection,
    run_id: int,
    agent: str,
    other: str | None = None,
    first_tick: int = 0,
    last_tick: int | None = None,
) -> list[dict[str, Any]]:
    """Every trust change on the agent's ties (optionally only with `other`), oldest first."""
    last = last_tick if last_tick is not None else 1 << 62
    owned, params = _owned(conn, run_id)
    rows = conn.execute(
        f"""select * from trust_changes where {owned} and (a = ? or b = ?)
            and tick between ? and ? order by tick, rowid""",
        (*params, agent, agent, first_tick, last),
    ).fetchall()
    changes = [_without_run(row) for row in rows]
    if other:
        changes = [c for c in changes if other in (c["a"], c["b"])]
    return changes


def flows(
    conn: sqlite3.Connection,
    run_id: int,
    agent: str,
    first_tick: int = 0,
    last_tick: int | None = None,
) -> list[dict[str, Any]]:
    """The agent's ledger entries (full-level runs), oldest first."""
    last = last_tick if last_tick is not None else 1 << 62
    owned, params = _owned(conn, run_id)
    rows = conn.execute(
        f"""select tick, asset, category, amount, counterparty, event_id from flows
            where {owned} and agent_id = ? and tick between ? and ? order by tick, rowid""",
        (*params, agent, first_tick, last),
    )
    return [dict(row) for row in rows]


def agent_totals(conn: sqlite3.Connection, run_id: int, agent: str) -> list[dict[str, Any]]:
    """The agent's lifetime ledger totals by asset and category (every recording level)."""
    rows = conn.execute(
        "select asset, category, amount from agent_totals where run_id = ? and agent_id = ?",
        (run_id, agent),
    )
    return [dict(row) for row in rows]


def communities(conn: sqlite3.Connection, run_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        "select * from communities where run_id = ? order by community_id", (run_id,)
    )
    return [_without_run(row) for row in rows]


def community_sizes(conn: sqlite3.Connection, run_id: int) -> dict[int, list[tuple[int, int]]]:
    """community id -> [(tick, size), ...] (full-level runs only)."""
    sizes: dict[int, list[tuple[int, int]]] = {}
    owned, params = _owned(conn, run_id)
    rows = conn.execute(
        f"select community_id, tick, size from community_ticks where {owned} order by tick",
        params,
    )
    for row in rows:
        sizes.setdefault(row["community_id"], []).append((row["tick"], row["size"]))
    return sizes


def community_members(conn: sqlite3.Connection, run_id: int, tick: int) -> dict[int, list[str]]:
    """community id -> members at the latest detection at or before `tick`."""
    owned, params = _owned(conn, run_id)
    row = conn.execute(
        f"select max(tick) as t from community_ticks where {owned} and tick <= ?",
        (*params, tick),
    ).fetchone()
    if row is None or row["t"] is None:
        return {}
    rows = conn.execute(
        f"select community_id, members from community_ticks where {owned} and tick = ?",
        (*params, row["t"]),
    )
    return {r["community_id"]: json.loads(r["members"]) for r in rows}


def experiment_runs(conn: sqlite3.Connection, experiment: str) -> list[dict[str, Any]]:
    """(label, seed, run_id, scenario, overrides) for every job of the experiment with a
    finished run."""
    rows = conn.execute(
        """select x.label, x.seed, x.run_id, r.scenario, r.overrides from experiment_runs x
           join runs r on r.id = x.run_id
           where x.experiment = ? and r.status = 'done' order by x.label, x.seed""",
        (experiment,),
    )
    return [{**dict(row), "overrides": json.loads(row["overrides"])} for row in rows]


def all_measures(conn: sqlite3.Connection, run_ids: list[int]) -> dict[int, dict[str, float]]:
    """run id -> {measure: value} for many runs at once."""
    result: dict[int, dict[str, float]] = {run_id: {} for run_id in run_ids}
    for start in range(0, len(run_ids), 500):
        chunk = run_ids[start : start + 500]
        rows = conn.execute(
            f"select run_id, name, value from run_measures "
            f"where run_id in ({', '.join('?' for _ in chunk)})",
            chunk,
        )
        for row in rows:
            result[row["run_id"]][row["name"]] = row["value"]
    return result


def community_history(conn: sqlite3.Connection, run_id: int, community_id: int) -> list[dict]:
    """The community at every detection: size, members and internal stats (full-level runs)."""
    owned, params = _owned(conn, run_id)
    rows = conn.execute(
        f"""select tick, size, members, density, trust, trade from community_ticks
            where {owned} and community_id = ? order by tick""",
        (*params, community_id),
    )
    return [{**dict(row), "members": json.loads(row["members"])} for row in rows]


def org_history(conn: sqlite3.Connection, run_id: int, org_id: str) -> list[dict]:
    owned, params = _owned(conn, run_id)
    rows = conn.execute(
        f"""select tick, name, size, members, density, trust from org_ticks
            where {owned} and org_id = ? order by tick""",
        (*params, org_id),
    )
    return [{**dict(row), "members": json.loads(row["members"])} for row in rows]


def measures(conn: sqlite3.Connection, run_id: int) -> dict[str, float]:
    rows = conn.execute("select name, value from run_measures where run_id = ?", (run_id,))
    return {row["name"]: row["value"] for row in rows}


def event_counts(conn: sqlite3.Connection, run_id: int, since_tick: int = 0) -> dict[str, int]:
    owned, params = _owned(conn, run_id)
    rows = conn.execute(
        f"select kind, count(*) as n from events where {owned} and tick >= ? group by kind",
        (*params, since_tick),
    )
    return {row["kind"]: row["n"] for row in rows}


def _without_run(row: sqlite3.Row) -> dict[str, Any]:
    """A row as a dict, without its run id (a branch's history mixes rows of several runs)."""
    return {k: row[k] for k in row.keys() if k != "run_id"}


def _run_dict(row: sqlite3.Row) -> dict[str, Any]:
    run = dict(row)
    run["overrides"] = json.loads(run["overrides"])
    run["interventions"] = json.loads(run.get("interventions") or "[]")
    run.pop("config_json", None)
    return run


def _event_dict(conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    causes = conn.execute(
        "select cause_id from event_causes where run_id = ? and event_id = ? order by cause_id",
        (row["run_id"], row["id"]),
    ).fetchall()
    return {
        "id": row["id"],
        "tick": row["tick"],
        "kind": row["kind"],
        "subjects": json.loads(row["subjects"]),
        "message": row["message"],
        "cause": row["cause"],
        "detail": bool(row["detail"]),
        "caused_by": [c["cause_id"] for c in causes],
    }
