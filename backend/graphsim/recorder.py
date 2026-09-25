"""Turns a running world into rows for storage.py, tick by tick.

The recorder only reads the world (never its random generator), so recording can't change what
a simulation does. What it keeps depends on the recording level (scenario.toml [recording]).
"""

import gzip
import json

from graphsim import analysis, serialize
from graphsim.config import RecordingSpec
from graphsim.events import Event
from graphsim.model import Layer, World
from graphsim.storage import Batch


class Recorder:
    def __init__(self, world: World, spec: RecordingSpec) -> None:
        self.world = world
        self.spec = spec
        self.batch = Batch()
        self.founding = set(world.agents)
        self.lifetimes: dict[str, list] = {}  # agent id -> row for the agents table
        self.changed_lifetimes: dict[str, None] = {}  # rows to (re)write at the next flush
        # Every tick's metrics, kept in memory for the run's measures, so a run's measures don't
        # depend on how often its metrics are stored.
        self.all_metrics: dict[str, list[tuple[int, float]]] = {}
        self.detections_seen = 0
        self._note_arrivals()
        if spec.snapshots:
            self._snapshot()

    def after_tick(self, events: list[Event]) -> None:
        world, spec = self.world, self.spec
        tick = world.tick
        for name, value in world.metrics.history[-1].items():
            if name != "tick":
                self.all_metrics.setdefault(name, []).append((tick, float(value)))
        self._note_arrivals()
        self._record_events(events)
        if tick == 1 or tick % spec.metrics_every == 0:
            self._record_metrics()
        if spec.agent_history_every and tick % spec.agent_history_every == 0:
            self._record_agents()
        if spec.trust_ledger:
            self.batch.trust_changes += [
                (tick, c.a, c.b, c.before, c.after, c.event_id) for c in world.trust_changes
            ]
        if spec.community_history and world.metrics.detections != self.detections_seen:
            self._record_communities()
        self.detections_seen = world.metrics.detections
        if spec.snapshots:
            self._snapshot()

    def flush(self) -> Batch:
        """Everything recorded since the last flush."""
        batch = self.batch
        batch.ticks_done = self.world.tick
        batch.agents = [tuple(self.lifetimes[a]) for a in self.changed_lifetimes]
        self.changed_lifetimes = {}
        self.batch = Batch()
        return batch

    def finish(self) -> Batch:
        """The last batch, with community records and the run-level measures."""
        world = self.world
        if world.tick % self.spec.metrics_every != 0:
            self._record_metrics()  # always store the final tick
        batch = self.flush()
        records = [
            analysis.community_row(record, world.tick)
            for record in world.metrics.communities.values()
        ]
        batch.communities = [
            (
                r["community_id"], r["born"], r["died"], r["fate"], r["parent"], r["merged_into"],
                r["peak_size"], r["members_ever"], r["mean_turnover"], r["continuations"],
            )
            for r in records
        ]  # fmt: skip
        batch.measures = analysis.compute_measures(
            analysis.RunData(
                series=self.all_metrics,
                communities=records,
                event_counts=_count_kinds(world.log.events),
                ticks=world.tick,
                min_lifespan=world.cfg.metrics.community_min_lifespan,
            )
        )
        return batch

    # --- pieces ---

    def _note_arrivals(self) -> None:
        for agent in self.world.agents.values():
            if agent.id not in self.lifetimes:
                self.lifetimes[agent.id] = [
                    agent.id, agent.name, agent.occupation, agent.home,
                    agent.arrived, None, None, int(agent.id in self.founding),
                ]  # fmt: skip
                self.changed_lifetimes[agent.id] = None

    def _record_events(self, events: list[Event]) -> None:
        batch = self.batch
        for event in events:
            if event.kind == "left" and event.subjects[0] in self.lifetimes:
                row = self.lifetimes[event.subjects[0]]
                row[5], row[6] = event.tick, event.id  # departed, departure_event
                self.changed_lifetimes[event.subjects[0]] = None
            if event.detail and not self.spec.detail_events:
                continue
            batch.events.append(
                (
                    event.id, event.tick, event.kind, json.dumps(list(event.subjects)),
                    event.message, event.cause, int(event.detail),
                )
            )  # fmt: skip
            batch.event_subjects += [(entity, event.id) for entity in dict.fromkeys(event.subjects)]
            batch.event_causes += [(event.id, cause) for cause in dict.fromkeys(event.caused_by)]

    def _record_metrics(self) -> None:
        latest = self.world.metrics.history[-1]
        tick = int(latest["tick"])
        for name, value in latest.items():
            if name == "tick":
                continue
            self.batch.metrics.append((tick, name, float(value)))

    def _record_agents(self) -> None:
        world = self.world
        tick = world.tick
        activity = _activity(world)
        for agent in world.agents.values():
            social = world.edges_of(agent.id, Layer.SOCIAL)
            stats = world.metrics.node_stats.get(agent.id)
            counts = activity.get(agent.id, {})
            self.batch.agent_ticks.append(
                (
                    agent.id, tick, agent.occupation, world.org_of(agent.id),
                    stats.community if stats else -1, round(agent.coin, 3),
                    json.dumps({g: round(v, 3) for g, v in agent.inventory.items()}),
                    round(sum(e.trust for e in social) / len(social), 4) if social else None,
                    len(social), len(world.edges_of(agent.id, Layer.TRADE)),
                    round(stats.betweenness, 4) if stats else 0.0,
                    counts.get("bought", 0), counts.get("sold", 0), counts.get("brokered", 0),
                    counts.get("gifts_given", 0), counts.get("gifts_received", 0),
                    agent.hunger_ticks,
                )
            )  # fmt: skip

    def _record_communities(self) -> None:
        world = self.world
        for cid in world.metrics.alive:
            record = world.metrics.communities[cid]
            members = json.dumps(sorted(record.members))
            self.batch.community_ticks.append((world.tick, cid, len(record.members), members))

    def _snapshot(self) -> None:
        state = serialize.snapshot(self.world, [])
        del state["events"]  # events are stored (and queried) separately
        data = gzip.compress(json.dumps(state, separators=(",", ":")).encode(), compresslevel=6)
        self.batch.snapshots.append((self.world.tick, data))


def _activity(world: World) -> dict[str, dict[str, int]]:
    """Per agent, how many trades it made this tick as buyer, seller or broker, and gifts."""
    counts: dict[str, dict[str, int]] = {}

    def bump(agent_id: str | None, what: str) -> None:
        if agent_id:
            per_agent = counts.setdefault(agent_id, {})
            per_agent[what] = per_agent.get(what, 0) + 1

    for interaction in world.interactions:
        if interaction.outcome == "success":
            bump(interaction.buyer, "bought")
            bump(interaction.seller, "sold")
            bump(interaction.broker, "brokered")
        elif interaction.outcome == "gift":
            bump(interaction.seller, "gifts_given")
            bump(interaction.buyer, "gifts_received")
    return counts


def _count_kinds(events: list[Event]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for event in events:
        counts[event.kind] = counts.get(event.kind, 0) + 1
    return counts
