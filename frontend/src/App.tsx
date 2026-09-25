import { useEffect, useRef, useState } from "react";
import { useSimulation } from "./api";
import { Controls } from "./Controls";
import { EventFeed } from "./EventFeed";
import { GraphView } from "./GraphView";
import { Inspector } from "./Inspector";
import { Legend } from "./Legend";
import { MetricsBar } from "./MetricsBar";
import { LAYERS, type Layer } from "./types";

export function App() {
  const { snapshot, connected, recentEvents, send } = useSimulation();
  const [visibleLayers, setVisibleLayers] = useState<Set<Layer>>(new Set(LAYERS));
  const [selectedId, setSelectedId] = useState<string | null>(null);

  // A reset starts a new world, where the selected id may mean someone else: clear it.
  const lastTick = useRef(0);
  useEffect(() => {
    if (snapshot && snapshot.tick < lastTick.current) setSelectedId(null);
    lastTick.current = snapshot?.tick ?? 0;
  }, [snapshot]);

  function toggleLayer(layer: Layer) {
    setVisibleLayers((old) => {
      const next = new Set(old);
      if (next.has(layer)) next.delete(layer);
      else next.add(layer);
      return next;
    });
  }

  if (!snapshot) {
    return <div className="loading">Connecting to the simulation server on port 8000…</div>;
  }

  const liveIds = new Set(snapshot.nodes.map((n) => n.id));

  return (
    <div className="app">
      <Controls
        snapshot={snapshot}
        connected={connected}
        send={send}
        visibleLayers={visibleLayers}
        onToggleLayer={toggleLayer}
      />
      <MetricsBar snapshot={snapshot} onSelect={setSelectedId} />
      <main className="main">
        <div className="graph-panel">
          <GraphView
            snapshot={snapshot}
            visibleLayers={visibleLayers}
            selectedId={selectedId}
            onSelect={setSelectedId}
          />
          <Legend />
        </div>
        <Inspector snapshot={snapshot} selectedId={selectedId} onSelect={setSelectedId} />
      </main>
      <EventFeed events={recentEvents} liveIds={liveIds} onSelect={setSelectedId} />
    </div>
  );
}
