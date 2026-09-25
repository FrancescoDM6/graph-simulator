import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { CHART_BACKGROUND } from "./charts/LineChart";
import { ExportMenu } from "./ExportMenu";
import { figureFromElement, fileStem, runDescription } from "./export";
import { communityColor } from "./graphStyle";
import { useElementWidth } from "./hooks/useElementWidth";
import type { CommunityRow, RunInfo } from "./types";

const ROW_HEIGHT = 16;
const MIN_LIFESPAN = 5; // shorter-lived communities are detection flicker (scenario.toml [metrics])

interface Props {
  runId: number;
  run: RunInfo | undefined;
  lastTick: number;
  cursor: number;
  selected: number | null;
  onSelect: (communityId: number | null, tick: number) => void;
}

/** Every community's life as a bar: when it was born, when it died and how (merged into
 * another, split up, dissolved), and where it came from. Click one to highlight its members. */
export function Communities({ runId, run, lastTick, cursor, selected, onSelect }: Props) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [rows, setRows] = useState<CommunityRow[]>([]);
  const [showFlicker, setShowFlicker] = useState(false);
  const [ref, width] = useElementWidth<HTMLDivElement>();

  useEffect(() => {
    api.communities(runId).then((data) => setRows(data.communities));
  }, [runId, lastTick]);

  const lifespan = (c: CommunityRow) => (c.died ?? lastTick) - c.born;
  const firstDetection = Math.min(...rows.map((c) => c.born));
  const founding = (c: CommunityRow) => c.born === firstDetection;
  const shown = rows.filter((c) => showFlicker || lifespan(c) >= MIN_LIFESPAN || founding(c));
  const labelWidth = 150;
  const x = (tick: number) => labelWidth + (tick / Math.max(1, lastTick)) * Math.max(10, width - labelWidth - 8);

  return (
    <section className="communities">
      <div className="panel-header">
        <span>
          Communities <span className="muted">({shown.length} shown)</span>
        </span>
        <span className="header-options">
          <label>
            <input type="checkbox" checked={showFlicker} onChange={(e) => setShowFlicker(e.target.checked)} />{" "}
            include ones shorter than {MIN_LIFESPAN} ticks
          </label>
          <ExportMenu
            stem={fileStem(run, "communities")}
            title="Community lifespans"
            description={`${runDescription(run)}; bars: lifespans; ← parent it split from; → community it merged into`}
            figure={() => (svgRef.current ? figureFromElement(svgRef.current, CHART_BACKGROUND) : null)}
            rows={() => [
              ["community", "born", "died", "fate", "parent", "merged_into", "peak_size", "members_ever", "mean_turnover"],
              ...rows.map((c) => [c.community_id, c.born, c.died, c.fate, c.parent, c.merged_into, c.peak_size, c.members_ever, c.mean_turnover]),
            ]}
          />
        </span>
      </div>
      <div className="swimlanes" ref={ref}>
        {rows.length === 0 && <div className="muted">No community records (still computing?)</div>}
        {width > 0 && (
          <svg ref={svgRef} width={width} height={shown.length * ROW_HEIGHT + 4}>
            {shown.map((c, i) => {
              const y = i * ROW_HEIGHT + 2;
              const end = c.died ?? lastTick;
              const origin = c.parent !== null ? `← ${c.parent}` : founding(c) ? "at start" : "new";
              const fate =
                c.fate === "merged" ? `→ ${c.merged_into}` : c.fate === "alive" ? "" : c.fate;
              return (
                <g
                  key={c.community_id}
                  className={`lane ${selected === c.community_id ? "selected" : ""}`}
                  onClick={() => onSelect(c.community_id, Math.min(Math.max(cursor, c.born), end))}
                >
                  <title>
                    {`Community ${c.community_id}: ticks ${c.born}–${c.died ?? "end"}, peak ${c.peak_size} members, `}
                    {`${c.members_ever} ever, turnover ${(c.mean_turnover * 100).toFixed(1)}% per tick`}
                  </title>
                  <text className="lane-label" x={4} y={y + 11}>
                    #{c.community_id} {origin}
                  </text>
                  <rect
                    x={x(c.born)}
                    y={y + 2}
                    width={Math.max(2, x(end) - x(c.born))}
                    height={ROW_HEIGHT - 5}
                    rx={2}
                    fill={communityColor(c.community_id)}
                  />
                  <text className="lane-fate" x={x(end) + 4} y={y + 11}>
                    {fate}
                  </text>
                </g>
              );
            })}
            <line className="cursor-line" x1={x(cursor)} x2={x(cursor)} y1={0} y2={shown.length * ROW_HEIGHT + 4} />
          </svg>
        )}
      </div>
    </section>
  );
}
