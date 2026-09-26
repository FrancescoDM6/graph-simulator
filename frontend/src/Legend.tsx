import { useState } from "react";
import { type ColorMode, COLOR_MODES, LAYER_COLORS, numericValue, sequentialColor, STARVING_COLOR } from "./graphStyle";
import { ChevronIcon } from "./icons";
import type { AgentNode, Snapshot } from "./types";

interface Props {
  mode: ColorMode;
  occupationColors: Record<string, string>;
  townColors: Record<string, string>;
  snapshot: Snapshot;
}

/** Explains the visual encodings defined in graphStyle.ts, for the current colour mode.
 * Starts collapsed to a single "Legend" button, so it doesn't cover the graph. */
export function Legend({ mode, occupationColors, townColors, snapshot }: Props) {
  const [open, setOpen] = useState(false);
  const agents = snapshot.nodes.filter((n): n is AgentNode => n.kind === "agent");
  const values = agents.map((a) => numericValue(a, mode)).filter((v): v is number => v !== null);
  const modeLabel = COLOR_MODES.find(([m]) => m === mode)?.[1] ?? mode;
  const townName = (id: string) => snapshot.nodes.find((n) => n.id === id)?.name ?? id;

  return (
    <div className="floating legend">
      <button onClick={() => setOpen(!open)}>
        Legend <ChevronIcon up={!open} />
      </button>
      {open && (
        <div className="legend-body">
          <div className="label">Fill: {modeLabel}</div>
          {mode === "occupation" && (
            <div className="legend-row">
              {Object.entries(occupationColors).map(([occupation, color]) => (
                <span key={occupation}>
                  <span className="swatch-dot" style={{ background: color }} /> {occupation}
                </span>
              ))}
            </div>
          )}
          {mode === "town" && (
            <div className="legend-row">
              {Object.entries(townColors).map(([town, color]) => (
                <span key={town}>
                  <span className="swatch-dot" style={{ background: color }} /> {townName(town)}
                </span>
              ))}
            </div>
          )}
          {mode === "community" && <div>one colour per community</div>}
          {values.length > 0 && (
            <div className="gradient-row">
              {Math.min(...values).toFixed(2)}
              <span
                className="gradient"
                style={{
                  background: `linear-gradient(to right, ${[0, 0.25, 0.5, 0.75, 1].map(sequentialColor).join(",")})`,
                }}
              />
              {Math.max(...values).toFixed(2)}
            </div>
          )}
          <div className="label">Ring: occupation</div>
          <div className="legend-row">
            {Object.entries(occupationColors).map(([occupation, color]) => (
              <span key={occupation}>
                <span className="ring" style={{ borderColor: color }} /> {occupation}
              </span>
            ))}
            <span>
              <span className="ring" style={{ borderColor: STARVING_COLOR }} /> starving
            </span>
          </div>
          <div className="label">Size: coin</div>
          <div className="label">Ties</div>
          <div className="legend-row">
            {(["social", "trade"] as const).map((layer) => (
              <span key={layer}>
                <span className="swatch" style={{ background: LAYER_COLORS[layer] }} /> {layer}
              </span>
            ))}
          </div>
          <div className="faint">thicker = stronger · trade fades when idle</div>
          <div className="faint">▢ town · ◇ site · ⬡ organization</div>
        </div>
      )}
    </div>
  );
}
