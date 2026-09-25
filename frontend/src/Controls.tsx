import { useState } from "react";
import { LAYER_COLORS } from "./graphStyle";
import { LAYERS, type Command, type Layer, type Snapshot } from "./types";

interface Props {
  snapshot: Snapshot;
  connected: boolean;
  send: (command: Command) => void;
  visibleLayers: Set<Layer>;
  onToggleLayer: (layer: Layer) => void;
}

export function Controls({ snapshot, connected, send, visibleLayers, onToggleLayer }: Props) {
  const [seedText, setSeedText] = useState(String(snapshot.seed));
  const { running, ticks_per_second: speed } = snapshot;

  function reset() {
    const seed = Number.parseInt(seedText, 10);
    if (Number.isFinite(seed)) send({ command: "reset", seed });
  }

  return (
    <header className="controls">
      <div className="control-group">
        <button className="primary" onClick={() => send({ command: running ? "pause" : "play" })}>
          {running ? "Pause" : "Play"}
        </button>
        <button onClick={() => send({ command: "step" })} disabled={running}>
          Step
        </button>
        <label className="speed">
          <input
            type="range"
            min={1}
            max={30}
            value={speed}
            onChange={(e) => send({ command: "set_speed", ticks_per_second: Number(e.target.value) })}
          />
          {speed} ticks/s
        </label>
      </div>

      <div className="control-group">
        <label>
          Seed{" "}
          <input
            className="seed"
            value={seedText}
            onChange={(e) => setSeedText(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && reset()}
          />
        </label>
        <button onClick={reset}>Reset</button>
      </div>

      <div className="control-group layers">
        {LAYERS.map((layer) => (
          <label key={layer} className="layer-toggle">
            <input
              type="checkbox"
              aria-label={`show ${layer} layer`}
              checked={visibleLayers.has(layer)}
              onChange={() => onToggleLayer(layer)}
            />
            <span className="swatch" style={{ background: LAYER_COLORS[layer] }} />
            {layer}
          </label>
        ))}
      </div>

      <div className={`status ${connected ? "" : "offline"}`}>
        {connected ? `tick ${snapshot.tick}` : "reconnecting…"}
        {snapshot.drought && <span className="drought">drought</span>}
      </div>
    </header>
  );
}
