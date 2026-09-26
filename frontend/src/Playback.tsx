import { LAYER_COLORS } from "./graphStyle";
import { PauseIcon, PlayIcon, SidebarIcon, StepBackIcon, StepForwardIcon } from "./icons";
import { LAYERS, type Layer } from "./types";

interface Props {
  tick: number;
  lastTick: number; // the last tick that can be shown (grows while a run computes)
  totalTicks: number;
  playing: boolean;
  speed: number;
  drought: boolean;
  droughts: [number, number][]; // drawn on the scrubber's track
  onTick: (tick: number) => void;
  onPlaying: (playing: boolean) => void;
  onSpeed: (speed: number) => void;
  visibleLayers: Set<Layer>;
  onToggleLayer: (layer: Layer) => void;
  panelOpen: boolean;
  onTogglePanel: () => void;
}

/** Play/pause, stepping, a scrubber over the whole run (droughts marked on it), speed, layer
 * switches and the side panel switch. */
export function Playback(props: Props) {
  const { tick, lastTick, totalTicks, playing, speed, drought } = props;
  return (
    <div className="transport">
      <div className="buttons">
        <button
          className="primary icon-button"
          onClick={() => props.onPlaying(!playing)}
          title={playing ? "pause" : "play"}
        >
          {playing ? <PauseIcon /> : <PlayIcon />}
        </button>
        <button className="ghost icon-button" onClick={() => props.onTick(tick - 1)} disabled={tick <= 0} title="previous tick">
          <StepBackIcon />
        </button>
        <button
          className="ghost icon-button"
          onClick={() => props.onTick(tick + 1)}
          disabled={tick >= lastTick}
          title="next tick"
        >
          <StepForwardIcon />
        </button>
      </div>
      <input
        className="scrubber"
        type="range"
        min={0}
        max={Math.max(totalTicks, 1)}
        value={tick}
        aria-label="tick"
        style={{ "--track": scrubberTrack(tick, lastTick, totalTicks, props.droughts) } as React.CSSProperties}
        onChange={(e) => props.onTick(Math.min(lastTick, Number(e.target.value)))}
      />
      <span className="tick-readout" title={lastTick < totalTicks ? `computed up to tick ${lastTick}` : undefined}>
        <b>{tick}</b> / {totalTicks}
      </span>
      {drought && <span className="badge drought">DROUGHT</span>}
      <label className="speed" title="ticks per second">
        <input type="range" min={1} max={60} value={speed} onChange={(e) => props.onSpeed(Number(e.target.value))} />
        {speed}/s
      </label>
      <span className="divider" />
      <span className="layers">
        {LAYERS.map((layer) => (
          <button
            key={layer}
            className="chip"
            aria-pressed={props.visibleLayers.has(layer)}
            title={`show or hide the ${layer} layer`}
            onClick={() => props.onToggleLayer(layer)}
          >
            <span className="dot" style={{ background: LAYER_COLORS[layer] }} />
            {layer}
          </button>
        ))}
      </span>
      <span className="divider" />
      <button
        className={`ghost icon-button ${props.panelOpen ? "active" : ""}`}
        onClick={props.onTogglePanel}
        title={props.panelOpen ? "hide the side panel" : "show the side panel"}
      >
        <SidebarIcon />
      </button>
    </div>
  );
}

/** The scrubber's track as stacked CSS gradients: droughts on top, then the part already played,
 * the part computed but not played, and the part not computed yet. */
function scrubberTrack(tick: number, lastTick: number, totalTicks: number, droughts: [number, number][]): string {
  const at = (t: number) => `${((100 * t) / Math.max(1, totalTicks)).toFixed(2)}%`;
  const droughtStops = droughts.flatMap(([start, end]) => [
    `transparent ${at(start)}`,
    `rgba(232, 165, 75, 0.75) ${at(start)}`,
    `rgba(232, 165, 75, 0.75) ${at(end + 1)}`,
    `transparent ${at(end + 1)}`,
  ]);
  const droughtLayer = droughtStops.length ? `linear-gradient(to right, transparent 0%, ${droughtStops.join(", ")}), ` : "";
  const progress =
    `linear-gradient(to right, #6b7280 0%, #6b7280 ${at(tick)}, #2e343e ${at(tick)}, ` +
    `#2e343e ${at(lastTick)}, #171b21 ${at(lastTick)}, #171b21 100%)`;
  return droughtLayer + progress;
}
