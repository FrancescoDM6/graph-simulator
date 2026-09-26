import { useState } from "react";
import { COLOR_MODES, type ColorMode, PULSE_GROUPS, type PulseGroup } from "./graphStyle";
import { ChevronIcon } from "./icons";

interface Props {
  colorMode: ColorMode;
  onColorMode: (mode: ColorMode) => void;
  pulses: Set<PulseGroup>;
  onTogglePulse: (group: PulseGroup) => void;
  showHulls: boolean;
  onShowHulls: (show: boolean) => void;
  exportMenu: React.ReactNode;
}

/** The toolbar over the graph: colouring, community outlines, event highlights, export. */
export function GraphControls(props: Props) {
  const [open, setOpen] = useState(false);
  return (
    <div className="floating graph-toolbar">
      <span className="label">Colour</span>
      <select
        value={props.colorMode}
        onChange={(e) => props.onColorMode(e.target.value as ColorMode)}
        aria-label="colour agents by"
      >
        {COLOR_MODES.map(([mode, label]) => (
          <option key={mode} value={mode}>
            {label}
          </option>
        ))}
      </select>
      <button
        className="chip"
        aria-pressed={props.showHulls}
        onClick={() => props.onShowHulls(!props.showHulls)}
        title="draw an outline around each community"
      >
        Outlines
      </button>
      <span className="menu-anchor">
        <button
          className="chip"
          aria-pressed={props.pulses.size > 0}
          onClick={() => setOpen(!open)}
          title="flash events on the graph as playback passes them"
        >
          Events {props.pulses.size}/{PULSE_GROUPS.length} <ChevronIcon up={open} />
        </button>
        {open && (
          <div className="popover" onMouseLeave={() => setOpen(false)}>
            {PULSE_GROUPS.map(([group, label]) => (
              <label key={group} className="check">
                {label}
                <input type="checkbox" checked={props.pulses.has(group)} onChange={() => props.onTogglePulse(group)} />
              </label>
            ))}
          </div>
        )}
      </span>
      {props.exportMenu}
    </div>
  );
}
