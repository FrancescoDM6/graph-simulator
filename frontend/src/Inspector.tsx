import { useEffect, useState } from "react";
import { api } from "./api";
import { Attribution } from "./Attribution";
import { LineChart } from "./charts/LineChart";
import { fileStem, runDescription } from "./export";
import { formatNumber } from "./format";
import { communityColor, LAYER_COLORS } from "./graphStyle";
import {
  type AgentTick,
  type GraphEdge,
  type GraphNode,
  LAYERS,
  type RunInfo,
  type Series,
  type SimEvent,
  type Snapshot,
  type TrustEntry,
} from "./types";

const TRUST_WINDOW = 5; // clicking the trust chart lists changes from this many ticks before
const MILESTONE_KINDS = ["wealthy", "poor", "hub"].flatMap((s) => [`became_${s}`, `no_longer_${s}`]);

export type Group = { kind: "community"; id: number } | { kind: "org"; id: string };

interface Props {
  runId: number;
  run: RunInfo | undefined;
  snapshot: Snapshot;
  name: (id: string) => string; // any agent's name, including ones who have left
  ego: { id: string; hops: number } | null;
  onEgo: (ego: { id: string; hops: number } | null) => void;
  onOpenGroup: (group: Group) => void;
  selectedId: string | null;
  lastTick: number;
  droughts: [number, number][];
  stapleGood: string; // the good shown in the agent's charts (the first eaten good)
  onSelect: (id: string) => void;
  onJump: (tick: number) => void;
  onWhy: (eventId: number) => void;
}

/** The selected node at the cursor: its state, charts of its whole life, relationships and
 * history. */
export function Inspector(props: Props) {
  const { runId, snapshot, selectedId, onSelect, name, ego, onEgo, onOpenGroup } = props;
  const nodesById = new Map(snapshot.nodes.map((n) => [n.id, n]));

  if (!selectedId) {
    return (
      <aside className="inspector muted">
        Click a node to see its state, its whole life in charts, its relationships and its history.
      </aside>
    );
  }
  const node = nodesById.get(selectedId);
  return (
    <aside className="inspector">
      {node ? (
        <>
          <h2>{node.name}</h2>
          <div className="inspector-actions">
            {node.kind === "agent" && (
              <>
                ego view:
                {[1, 2].map((hops) => (
                  <button
                    key={hops}
                    className={`small-button ${ego?.id === node.id && ego.hops === hops ? "active" : ""}`}
                    onClick={() => onEgo({ id: node.id, hops })}
                  >
                    {hops} hop{hops > 1 ? "s" : ""}
                  </button>
                ))}
                {ego && (
                  <button className="small-button" onClick={() => onEgo(null)}>
                    off
                  </button>
                )}
                {node.community >= 0 && (
                  <button className="small-button" onClick={() => onOpenGroup({ kind: "community", id: node.community })}>
                    community {node.community} ›
                  </button>
                )}
                {node.org && (
                  <button className="small-button" onClick={() => onOpenGroup({ kind: "org", id: node.org! })}>
                    organization ›
                  </button>
                )}
              </>
            )}
            {node.kind === "org" && (
              <button className="small-button" onClick={() => onOpenGroup({ kind: "org", id: node.id })}>
                organization page ›
              </button>
            )}
          </div>
          <NodeState node={node} name={name} />
          {node.kind === "agent" && <AgentCharts {...props} agentId={node.id} />}
          {node.kind === "agent" && (
            <Attribution
              runId={runId}
              run={props.run}
              agentId={node.id}
              cursor={snapshot.tick}
              stapleGood={props.stapleGood}
              name={name}
              onJump={props.onJump}
              onWhy={props.onWhy}
            />
          )}
          <Relationships node={node} edges={snapshot.edges} name={name} onSelect={onSelect} />
        </>
      ) : (
        <h2 className="muted">Not in the world at tick {snapshot.tick}</h2>
      )}
      <History runId={runId} entityId={selectedId} cursor={snapshot.tick} onJump={props.onJump} onWhy={props.onWhy} />
    </aside>
  );
}

function NodeState({ node, name }: { node: GraphNode; name: (id: string) => string }) {
  const rows: [string, React.ReactNode][] = [];
  switch (node.kind) {
    case "agent":
      rows.push(
        ["Occupation", `${node.occupation} in ${name(node.home)}`],
        ["Coin", node.coin.toFixed(1)],
        [
          "Holding",
          Object.entries(node.inventory)
            .map(([good, amount]) => `${amount.toFixed(1)} ${good}`)
            .join(" · "),
        ],
        ["Needs", node.need || "nothing"],
        ["Hungry for", node.hunger_ticks ? `${node.hunger_ticks} ticks` : "–"],
        ["Organization", node.org ? name(node.org) : "–"],
        [
          "Community",
          node.community < 0 ? (
            "–"
          ) : (
            <span>
              <span className="dot" style={{ background: communityColor(node.community) }} />
              {node.community}
            </span>
          ),
        ],
        ["Broker score", `${Math.round(node.betweenness * 100)}% of trade paths`],
        ["Arrived", `tick ${node.arrived}`],
      );
      break;
    case "town":
      rows.push(["Residents", node.residents]);
      break;
    case "site":
      rows.push(["Kind", node.site_kind], ["Stock", `${node.stock.toFixed(0)} / ${node.capacity}`]);
      break;
    case "org":
      rows.push(["Members", node.members], ["Home", name(node.home)], ["Founded", `tick ${node.founded}`]);
      break;
  }
  return (
    <dl className="state">
      {rows.map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

/** Coin, staple food, trust and brokerage over the agent's whole life. Clicking the trust
 * chart lists the trust changes just before that tick, each with its cause. */
function AgentCharts({
  runId,
  run,
  agentId,
  snapshot,
  lastTick,
  droughts,
  stapleGood,
  name,
  onJump,
  onWhy,
}: Props & { agentId: string }) {
  const [history, setHistory] = useState<AgentTick[]>([]);
  const [milestones, setMilestones] = useState<SimEvent[]>([]);
  const [trustTick, setTrustTick] = useState<number | null>(null);
  const [trust, setTrust] = useState<TrustEntry[]>([]);

  useEffect(() => {
    setHistory([]);
    setMilestones([]);
    setTrustTick(null);
    api.agentHistory(runId, agentId).then((h) => setHistory(h.ticks));
    api.events(runId, { entity: agentId, kinds: MILESTONE_KINDS, limit: 200 }).then(setMilestones);
  }, [runId, agentId]);
  const markers = milestones.map((m) => ({ tick: m.tick, label: `${m.message}: ${m.cause}` }));
  const exportAs = (what: string) => ({
    stem: fileStem(run, agentId, what),
    description: `${name(agentId)} (${agentId}), ${runDescription(run)}`,
  });

  useEffect(() => {
    if (trustTick === null) return;
    api.trust(runId, agentId, trustTick - TRUST_WINDOW, trustTick).then(setTrust);
  }, [runId, agentId, trustTick]);

  const series = (value: (t: AgentTick) => number | null): Series =>
    history.flatMap((t) => {
      const v = value(t);
      return v === null ? [] : [[t.tick, v] as [number, number]];
    });
  const chart = (label: string, color: string, data: Series, what: string, onPick = onJump) => (
    <LineChart
      label={label}
      color={color}
      a={data}
      lastTick={lastTick}
      droughts={droughts}
      cursor={snapshot.tick}
      onPick={onPick}
      markers={markers}
      height={56}
      exportAs={exportAs(what)}
    />
  );
  const other = (entry: TrustEntry) => (entry.a === agentId ? entry.b : entry.a);

  return (
    <>
      <h3>Over time</h3>
      {history.length === 0 && <div className="muted small">No per-tick history stored for this run.</div>}
      {history.length > 0 && (
        <div className="agent-charts">
          {chart("Coin", "#f5d76e", series((t) => t.coin), "coin")}
          {chart(stapleGood, "#7bd88f", series((t) => t.inventory[stapleGood] ?? 0), stapleGood)}
          {chart("Mean trust (click for causes)", "#6ea8fe", series((t) => t.mean_trust), "trust", (tick) => {
            onJump(tick);
            setTrustTick(tick);
          })}
          {chart("Broker score", "#f0a04b", series((t) => t.betweenness), "broker-score")}
          {milestones.length > 0 && (
            <ul className="compact-list">
              {milestones.map((m) => (
                <li key={m.id}>
                  <button className="event-tick link" onClick={() => onJump(m.tick)}>
                    {m.tick}
                  </button>{" "}
                  <b>{m.message}</b> <span className="event-cause">{m.cause}</span>
                  <button className="link small why" onClick={() => onWhy(m.id)}>
                    why?
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      {trustTick !== null && (
        <div className="trust-ledger">
          <div className="small">
            Trust changes, ticks {trustTick - TRUST_WINDOW}–{trustTick}{" "}
            <button className="link small" onClick={() => setTrustTick(null)}>
              hide
            </button>
          </div>
          {trust.length === 0 && <div className="muted small">None.</div>}
          <ul>
            {trust.map((entry, i) => (
              <li key={i}>
                <span className="event-tick">{entry.tick}</span>
                <span className={entry.after >= entry.before ? "up" : "down"}>
                  {formatNumber(entry.before)} → {formatNumber(entry.after)}
                </span>{" "}
                with {name(other(entry))}
                {entry.event && <span className="event-cause"> {entry.event.message}</span>}
                <button className="link small why" onClick={() => onWhy(entry.event_id)}>
                  why?
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </>
  );
}

function Relationships({
  node,
  edges,
  name,
  onSelect,
}: {
  node: GraphNode;
  edges: GraphEdge[];
  name: (id: string) => string;
  onSelect: (id: string) => void;
}) {
  const mine = edges.filter((e) => e.source === node.id || e.target === node.id);
  if (mine.length === 0) return null;
  return (
    <>
      <h3>Relationships</h3>
      {LAYERS.map((layer) => {
        const ofLayer = mine.filter((e) => e.layer === layer).sort((a, b) => b.strength - a.strength);
        if (ofLayer.length === 0) return null;
        return (
          <div key={layer} className="relationship-layer">
            <div className="layer-name" style={{ color: LAYER_COLORS[layer] }}>
              {layer} ({ofLayer.length})
            </div>
            <ul>
              {ofLayer.map((edge) => {
                const other = edge.source === node.id ? edge.target : edge.source;
                return (
                  <li key={edge.id}>
                    <button className="link" onClick={() => onSelect(other)}>
                      {name(other)}
                    </button>
                    {(layer === "social" || layer === "trade") && (
                      <span className="muted">
                        {" "}
                        strength {edge.strength.toFixed(2)}
                        {edge.trust !== null && ` · trust ${edge.trust.toFixed(2)}`}
                      </span>
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
        );
      })}
    </>
  );
}

/** Everything that happened to the node up to the cursor, newest first. */
function History({
  runId,
  entityId,
  cursor,
  onJump,
  onWhy,
}: {
  runId: number;
  entityId: string;
  cursor: number;
  onJump: (tick: number) => void;
  onWhy: (eventId: number) => void;
}) {
  const [events, setEvents] = useState<SimEvent[]>([]);
  useEffect(() => {
    setEvents([]);
    api.events(runId, { entity: entityId, limit: 5000 }).then(setEvents);
  }, [runId, entityId]);
  const upToCursor = events.filter((e) => e.tick <= cursor).reverse();
  return (
    <>
      <h3>History</h3>
      <ol className="history">
        {upToCursor.map((event) => (
          <li key={event.id}>
            <button className="event-tick link" onClick={() => onJump(event.tick)}>
              Tick {event.tick}
            </button>
            <div>{event.message}</div>
            {event.cause && <div className="event-cause">{event.cause}</div>}
            {event.caused_by.length > 0 && (
              <button className="link small why" onClick={() => onWhy(event.id)}>
                why?
              </button>
            )}
          </li>
        ))}
        {upToCursor.length === 0 && <li className="muted">Nothing has happened yet.</li>}
      </ol>
    </>
  );
}
