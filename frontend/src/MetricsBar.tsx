import type { Snapshot } from "./types";

interface Props {
  snapshot: Snapshot;
  onSelect: (id: string) => void;
}

/** One row of whole-network numbers for the current tick. */
export function MetricsBar({ snapshot, onSelect }: Props) {
  const m = snapshot.metrics;
  if (!m) return <div className="metrics-bar muted">Press Play or Step to start the simulation.</div>;

  const broker = snapshot.nodes.find((n) => n.id === m.top_broker);
  const items: [string, string, string][] = [
    ["Population", `${m.population}`, `${m.farmers} farmers · ${m.miners} miners · ${m.merchants} merchants`],
    ["Communities", `${m.communities}`, "Louvain communities of 4+ agents (social layer)"],
    ["Components", `${m.social_components}`, "separate social groups of 3+ agents"],
    ["Density", m.social_density.toFixed(2), "share of possible social ties that exist"],
    ["Clustering", m.social_clustering.toFixed(2), "how often friends of friends are friends"],
    ["Avg trust", m.avg_trust.toFixed(2), "mean trust over social ties"],
    ["Gini", m.gini_coin.toFixed(2), "inequality of coin: 0 equal, 1 one agent has all"],
    ["Food / ore", `${m.price_food.toFixed(2)} / ${m.price_ore.toFixed(2)}`, "base prices"],
    ["Trades", `${m.trades} ✓ ${m.failed_trades} ✗`, "trade attempts this tick"],
    ["Starving", `${m.starving}`, "agents who couldn't eat this tick"],
    ["Orgs", `${m.orgs}`, "organizations"],
  ];

  return (
    <div className="metrics-bar">
      {items.map(([label, value, hint]) => (
        <div key={label} className="metric" title={hint}>
          <span className="metric-label">{label}</span>
          <span className="metric-value">{value}</span>
        </div>
      ))}
      <div className="metric" title="agent with the highest betweenness on the trade layer">
        <span className="metric-label">Top broker</span>
        {broker ? (
          <button className="link metric-value" onClick={() => onSelect(broker.id)}>
            {broker.name} ({Math.round(m.top_broker_betweenness * 100)}%)
          </button>
        ) : (
          <span className="metric-value">—</span>
        )}
      </div>
    </div>
  );
}
