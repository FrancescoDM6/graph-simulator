import { useState } from "react";
import { COLOR_MODES, type ColorMode, PULSE_GROUPS, type PulseGroup } from "./graphStyle";

interface Props {
  colorMode: ColorMode;
  onColorMode: (mode: ColorMode) => void;
  pulses: Set<PulseGroup>;
  onTogglePulse: (group: PulseGroup) => void;
  showHulls: boolean;
  onShowHulls: (show: boolean) => void;
  exportMenu: React.ReactNode;
}

/** Display options floating over the graph: colouring, event highlights, community outlines. */
export function GraphControls(props: Props) {
  const [open, setOpen] = useState(false);
  return (
    <div className="graph-controls">
      <label>
        colour by{" "}
        <select value={props.colorMode} onChange={(e) => props.onColorMode(e.target.value as ColorMode)}>
          {COLOR_MODES.map(([mode, label]) => (
            <option key={mode} value={mode}>
              {label}
            </option>
          ))}
        </select>
      </label>
      <label>
        <input type="checkbox" checked={props.showHulls} onChange={(e) => props.onShowHulls(e.target.checked)} />{" "}
        community outlines
      </label>
      <button className="small-button" onClick={() => setOpen(!open)}>
        highlight events ({props.pulses.size}) {open ? "▴" : "▾"}
      </button>
      {props.exportMenu}
      {open && (
        <div className="pulse-options">
          {PULSE_GROUPS.map(([group, label]) => (
            <label key={group}>
              <input type="checkbox" checked={props.pulses.has(group)} onChange={() => props.onTogglePulse(group)} />{" "}
              {label}
            </label>
          ))}
        </div>
      )}
    </div>
  );
}
