import { LEGEND } from "./graphStyle";

/** Explains the visual encodings defined in graphStyle.ts. */
export function Legend() {
  return (
    <div className="legend">
      <div className="legend-title">Agents</div>
      <div>size = coin · fill = community</div>
      {LEGEND.occupations.map(([occupation, color]) => (
        <div key={occupation}>
          <span className="ring" style={{ borderColor: color }} /> {occupation}
        </div>
      ))}
      <div>
        <span className="ring" style={{ borderColor: LEGEND.starving }} /> starving
      </div>
      <div className="legend-title">Other nodes</div>
      <div>▢ town · ◇ site · ⬡ organization</div>
      <div className="legend-title">Edges</div>
      <div>width = strength · trade fades when idle</div>
    </div>
  );
}
