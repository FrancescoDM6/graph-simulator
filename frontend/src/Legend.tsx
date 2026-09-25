import { type ColorMode, COLOR_MODES, numericValue, sequentialColor, STARVING_COLOR } from "./graphStyle";
import type { AgentNode, Snapshot } from "./types";

interface Props {
  mode: ColorMode;
  occupationColors: Record<string, string>;
  townColors: Record<string, string>;
  snapshot: Snapshot;
}

/** Explains the visual encodings defined in graphStyle.ts, for the current colour mode. */
export function Legend({ mode, occupationColors, townColors, snapshot }: Props) {
  const agents = snapshot.nodes.filter((n): n is AgentNode => n.kind === "agent");
  const values = agents.map((a) => numericValue(a, mode)).filter((v): v is number => v !== null);
  const modeLabel = COLOR_MODES.find(([m]) => m === mode)?.[1] ?? mode;
  const townName = (id: string) => snapshot.nodes.find((n) => n.id === id)?.name ?? id;

  return (
    <div className="legend">
      <div className="legend-title">Agents</div>
      <div>size = coin · fill = {modeLabel}</div>
      {mode === "occupation" &&
        Object.entries(occupationColors).map(([occupation, color]) => (
          <div key={occupation}>
            <span className="swatch-dot" style={{ background: color }} /> {occupation}
          </div>
        ))}
      {mode === "town" &&
        Object.entries(townColors).map(([town, color]) => (
          <div key={town}>
            <span className="swatch-dot" style={{ background: color }} /> {townName(town)}
          </div>
        ))}
      {values.length > 0 && (
        <div className="gradient-row">
          {Math.min(...values).toFixed(2)}
          <span
            className="gradient"
            style={{ background: `linear-gradient(to right, ${[0, 0.25, 0.5, 0.75, 1].map(sequentialColor).join(",")})` }}
          />
          {Math.max(...values).toFixed(2)}
        </div>
      )}
      <div className="legend-title">Border</div>
      {Object.entries(occupationColors).map(([occupation, color]) => (
        <div key={occupation}>
          <span className="ring" style={{ borderColor: color }} /> {occupation}
        </div>
      ))}
      <div>
        <span className="ring" style={{ borderColor: STARVING_COLOR }} /> starving
      </div>
      <div className="legend-title">Other nodes</div>
      <div>▢ town · ◇ site · ⬡ organization</div>
      <div className="legend-title">Edges</div>
      <div>width = strength · trade fades when idle</div>
    </div>
  );
}
