import { useEffect, useRef, useState } from "react";
import { fetchHistory } from "./api";
import { communityColor, LAYER_COLORS } from "./graphStyle";
import { LAYERS, type GraphEdge, type GraphNode, type SimEvent, type Snapshot } from "./types";

interface Props {
  snapshot: Snapshot;
  selectedId: string | null;
  onSelect: (id: string) => void;
}

/** Current state, relationships and full history of the selected node. */
export function Inspector({ snapshot, selectedId, onSelect }: Props) {
  const history = useHistory(snapshot, selectedId);
  const nodesById = new Map(snapshot.nodes.map((n) => [n.id, n]));
  const name = (id: string) => nodesById.get(id)?.name ?? id;

  if (!selectedId) {
    return (
      <aside className="inspector muted">
        Click a node to see its state, relationships and history.
      </aside>
    );
  }
  const node = nodesById.get(selectedId);

  return (
    <aside className="inspector">
      {node ? (
        <>
          <h2>{node.name}</h2>
          <NodeState node={node} name={name} />
          <Relationships node={node} edges={snapshot.edges} name={name} onSelect={onSelect} />
        </>
      ) : (
        <h2 className="muted">No longer in the world</h2>
      )}
      <h3>History</h3>
      <ol className="history">
        {[...history].reverse().map((event, i) => (
          <li key={`${event.tick}-${i}`}>
            <span className="event-tick">Tick {event.tick}</span>
            <div>{event.message}</div>
            {event.cause && <div className="event-cause">{event.cause}</div>}
          </li>
        ))}
        {history.length === 0 && <li className="muted">Nothing has happened yet.</li>}
      </ol>
    </aside>
  );
}

/** Loads the node's history, and reloads it whenever a new tick mentions the node. */
function useHistory(snapshot: Snapshot, selectedId: string | null): SimEvent[] {
  const [history, setHistory] = useState<SimEvent[]>([]);
  const latestRequest = useRef(0);
  const mentionedThisTick =
    selectedId !== null && snapshot.events.some((e) => e.subjects.includes(selectedId));

  useEffect(() => {
    if (!selectedId) {
      setHistory([]);
      return;
    }
    const request = ++latestRequest.current;
    fetchHistory(selectedId)
      .then((events) => {
        if (request === latestRequest.current) setHistory(events); // ignore stale responses
      })
      .catch(() => setHistory([]));
    // Reload on a new selection, on a new world (seed/reset), or when this tick mentions the node.
  }, [selectedId, snapshot.seed, mentionedThisTick ? snapshot.tick : -1]);

  return history;
}

function NodeState({ node, name }: { node: GraphNode; name: (id: string) => string }) {
  const rows: [string, React.ReactNode][] = [];
  switch (node.kind) {
    case "agent":
      rows.push(
        ["Occupation", `${node.occupation} in ${name(node.home)}`],
        ["Coin", node.coin.toFixed(1)],
        ["Food / ore", `${node.food.toFixed(1)} / ${node.ore.toFixed(1)}`],
        ["Needs", node.need || "nothing"],
        ["Hungry for", node.hunger_ticks ? `${node.hunger_ticks} ticks` : "—"],
        ["Organization", node.org ? name(node.org) : "—"],
        [
          "Community",
          node.community < 0 ? "—" : (
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
