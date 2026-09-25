import { LAYER_COLORS } from "./graphStyle";
import { LAYERS, type Layer } from "./types";

interface Props {
  tick: number;
  lastTick: number; // the last tick that can be shown (grows while a run computes)
  totalTicks: number;
  playing: boolean;
  speed: number;
  drought: boolean;
  onTick: (tick: number) => void;
  onPlaying: (playing: boolean) => void;
  onSpeed: (speed: number) => void;
  visibleLayers: Set<Layer>;
  onToggleLayer: (layer: Layer) => void;
}

/** Play/pause, stepping, speed, a scrubber over the whole run, and layer toggles. */
export function Playback(props: Props) {
  const { tick, lastTick, totalTicks, playing, speed, drought } = props;
  return (
    <div className="playback">
      <button className="primary" onClick={() => props.onPlaying(!playing)}>
        {playing ? "Pause" : "Play"}
      </button>
      <button onClick={() => props.onTick(tick - 1)} disabled={tick <= 0} title="previous tick">
        ◀
      </button>
      <button onClick={() => props.onTick(tick + 1)} disabled={tick >= lastTick} title="next tick">
        ▶
      </button>
      <input
        className="scrubber"
        type="range"
        min={0}
        max={Math.max(lastTick, 1)}
        value={tick}
        onChange={(e) => props.onTick(Number(e.target.value))}
      />
      <span className="tick-label">
        tick {tick} / {totalTicks}
        {lastTick < totalTicks && <span className="muted"> (computed to {lastTick})</span>}
      </span>
      {drought && <span className="drought">drought</span>}
      <label className="speed">
        <input type="range" min={1} max={60} value={speed} onChange={(e) => props.onSpeed(Number(e.target.value))} />
        {speed}/s
      </label>
      <span className="layers">
        {LAYERS.map((layer) => (
          <label key={layer} className="layer-toggle">
            <input
              type="checkbox"
              aria-label={`show ${layer} layer`}
              checked={props.visibleLayers.has(layer)}
              onChange={() => props.onToggleLayer(layer)}
            />
            <span className="swatch" style={{ background: LAYER_COLORS[layer] }} />
            {layer}
          </label>
        ))}
      </span>
    </div>
  );
}
