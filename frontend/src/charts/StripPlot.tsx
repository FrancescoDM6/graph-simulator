import { useRef } from "react";
import { ExportMenu } from "../ExportMenu";
import { figureFromElement } from "../export";
import { useElementWidth } from "../hooks/useElementWidth";
import { FIGURE_BACKGROUND } from "../theme";

export interface StripRow {
  label: string;
  points: { value: number; runId: number; seed: number; present?: boolean }[];
  median: number | null;
  note?: string; // shown at the right end of the row
}

interface Props {
  rows: StripRow[];
  threshold?: number | null; // e.g. a phenomenon's "present if" value
  onPick: (runId: number) => void;
  exportAs?: { stem: string; title: string; description: string };
}

const ROW_HEIGHT = 26;
const LABEL_WIDTH = 210;
const NOTE_WIDTH = 200;

/** One row of dots per variant: every run's value of a measure, its median, and a threshold. */
export function StripPlot({ rows, threshold, onPick, exportAs }: Props) {
  const [ref, width] = useElementWidth<HTMLDivElement>();
  const svgRef = useRef<SVGSVGElement>(null);
  const values = rows.flatMap((r) => r.points.map((p) => p.value)).filter(Number.isFinite);
  if (threshold !== null && threshold !== undefined) values.push(threshold);
  const low = Math.min(...values, 0);
  const high = Math.max(...values, low + 1e-9);
  const plotWidth = Math.max(20, width - LABEL_WIDTH - NOTE_WIDTH - 10);
  const x = (v: number) => LABEL_WIDTH + ((v - low) / (high - low)) * plotWidth;
  const height = rows.length * ROW_HEIGHT + 18;

  return (
    <div className="strip-plot line-chart" ref={ref}>
      {exportAs && (
        <ExportMenu
          stem={exportAs.stem}
          title={exportAs.title}
          description={exportAs.description}
          figure={() => (svgRef.current ? figureFromElement(svgRef.current, FIGURE_BACKGROUND) : null)}
          rows={() => [
            ["variant", "seed", "run_id", "value", "present"],
            ...rows.flatMap((r) => r.points.map((p) => [r.label, p.seed, p.runId, p.value, p.present ?? ""])),
          ]}
        />
      )}
      {width > 0 && (
        <svg ref={svgRef} width={width} height={height}>
          {threshold !== null && threshold !== undefined && (
            <line className="threshold" x1={x(threshold)} x2={x(threshold)} y1={0} y2={height - 16} />
          )}
          {rows.map((row, i) => {
            const y = i * ROW_HEIGHT + ROW_HEIGHT / 2;
            return (
              <g key={row.label}>
                {i % 2 === 0 && <rect className="row-band" x={0} y={i * ROW_HEIGHT} width={width} height={ROW_HEIGHT} rx={4} />}
                <text className="lane-label" x={8} y={y + 4}>
                  {row.label}
                </text>
                {row.points.map((p, j) => (
                  <circle
                    key={p.runId}
                    className={`dot ${p.present === false ? "absent" : ""}`}
                    cx={x(p.value)}
                    cy={y + ((j % 5) - 2) * 1.6} // small jitter so identical values stay visible
                    r={3}
                    onClick={() => onPick(p.runId)}
                  >
                    <title>{`seed ${p.seed}: ${p.value.toFixed(3)} (click to open run #${p.runId})`}</title>
                  </circle>
                ))}
                {row.median !== null && (
                  <line className="median" x1={x(row.median)} x2={x(row.median)} y1={y - 9} y2={y + 9} />
                )}
                {row.note && (
                  <text className="lane-fate" x={LABEL_WIDTH + plotWidth + 12} y={y + 4}>
                    {row.note}
                  </text>
                )}
              </g>
            );
          })}
          <text className="chart-axis" x={LABEL_WIDTH} y={height - 3}>
            {low.toFixed(2)}
          </text>
          <text className="chart-axis" x={LABEL_WIDTH + plotWidth} y={height - 3} textAnchor="end">
            {high.toFixed(2)}
          </text>
        </svg>
      )}
    </div>
  );
}
