import { useRef } from "react";
import { ExportMenu } from "../ExportMenu";
import { figureFromElement } from "../export";
import { useElementWidth } from "../hooks/useElementWidth";
import { FIGURE_BACKGROUND, THEME } from "../theme";

export interface Bar {
  label: string;
  value: number; // positive bars grow right, negative left
  note?: string;
}

interface Props {
  title: string;
  bars: Bar[];
  exportAs?: { stem: string; description: string };
}

const ROW = 20;
const LABEL = 110;
const VALUE = 64;

/** Horizontal bars around zero, e.g. where an agent's coin came from and went. */
export function BarChart({ title, bars, exportAs }: Props) {
  const [ref, width] = useElementWidth<HTMLDivElement>();
  const svgRef = useRef<SVGSVGElement>(null);
  const extent = Math.max(1e-9, ...bars.map((b) => Math.abs(b.value)));
  const plot = Math.max(20, width - LABEL - VALUE - 8);
  const hasNegative = bars.some((b) => b.value < 0);
  const zero = LABEL + (hasNegative ? plot / 2 : 0);
  const scale = (hasNegative ? plot / 2 : plot) / extent;
  const height = bars.length * ROW + 20;

  return (
    <div className="line-chart bar-chart" ref={ref}>
      {exportAs && (
        <ExportMenu
          stem={exportAs.stem}
          title={title}
          description={exportAs.description}
          figure={() => (svgRef.current ? figureFromElement(svgRef.current, FIGURE_BACKGROUND) : null)}
          rows={() => [["label", "value", "note"], ...bars.map((b) => [b.label, b.value, b.note ?? ""])]}
        />
      )}
      {width > 0 && (
        <svg ref={svgRef} width={width} height={height}>
          <text className="chart-label" x={0} y={12}>
            {title}
          </text>
          {bars.map((bar, i) => {
            const y = 18 + i * ROW;
            const length = Math.abs(bar.value) * scale;
            return (
              <g key={bar.label}>
                <text className="chart-axis bar-label" x={LABEL - 6} y={y + 11} textAnchor="end">
                  {bar.label}
                </text>
                <rect
                  x={bar.value >= 0 ? zero : zero - length}
                  y={y + 2}
                  width={Math.max(1, length)}
                  height={ROW - 6}
                  rx={2}
                  fill={bar.value >= 0 ? THEME.good : THEME.danger}
                  opacity={0.85}
                >
                  {bar.note && <title>{bar.note}</title>}
                </rect>
                <text className="chart-axis" x={width - 4} y={y + 11} textAnchor="end">
                  {bar.value >= 0 ? "+" : ""}
                  {bar.value.toFixed(1)}
                </text>
              </g>
            );
          })}
          <line className="zero-line" x1={zero} x2={zero} y1={16} y2={height} />
        </svg>
      )}
    </div>
  );
}
