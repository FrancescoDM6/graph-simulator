import type { Snapshot } from "./types";

interface Props {
  snapshot: Snapshot | null;
  onSelect: (id: string) => void;
}

/** One line of whole-network numbers at the cursor (hover a number for what it means). */
export function MetricsBar({ snapshot, onSelect }: Props) {
  const m = snapshot?.metrics;
  if (!snapshot || !m) return <div className="stats faint">Tick 0: the world as it was built.</div>;

  const byPrefix = (prefix: string) =>
    Object.entries(m)
      .filter(([name]) => name.startsWith(prefix))
      .map(([name, value]) => [name.slice(prefix.length), value] as const);
  const broker = snapshot.nodes.find((n) => n.id === snapshot.top_broker);
  const items: [string, string, string][] = [
    [
      "Population",
      `${m.population}`,
      byPrefix("population.")
        .map(([occupation, n]) => `${n} ${occupation}s`)
        .join(" · "),
    ],
    ["Communities", `${m.communities}`, "Louvain communities (social layer)"],
    ["Components", `${m.social_components}`, "separate social groups"],
    ["Density", m.social_density.toFixed(2), "share of possible social ties that exist"],
    ["Clustering", m.social_clustering.toFixed(2), "how often friends of friends are friends"],
    ["Trust", m.avg_trust.toFixed(2), "mean trust over social ties"],
    ["Gini", m.gini_coin.toFixed(2), "inequality of coin: 0 equal, 1 one agent has all"],
    [
      "Prices",
      byPrefix("price.")
        .map(([, price]) => price.toFixed(2))
        .join(" / "),
      byPrefix("price.")
        .map(([good]) => good)
        .join(" / "),
    ],
    ["Trades", `${m.trades} ✓ ${m.failed_trades} ✗`, "trade attempts this tick: succeeded, failed"],
    ["Gifts", `${m.gifts}`, "gifts this tick"],
    ["Starving", `${m.starving}`, "agents who couldn't eat this tick"],
  ];
  return (
    <div className="stats">
      {items.map(([label, value, hint]) => (
        <span key={label} className="stat" title={hint}>
          <span className="stat-label">{label}</span>
          <span className="stat-value">{value}</span>
        </span>
      ))}
      <span className="stat" title="agent with the highest betweenness on the trade layer">
        <span className="stat-label">Top broker</span>
        {broker ? (
          <button className="link" onClick={() => onSelect(broker.id)}>
            {broker.name} ({Math.round((m.top_broker_betweenness ?? 0) * 100)}%)
          </button>
        ) : (
          <span className="stat-value">–</span>
        )}
      </span>
    </div>
  );
}
