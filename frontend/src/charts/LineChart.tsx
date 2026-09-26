import { useId, useRef } from "react";
import { ExportMenu } from "../ExportMenu";
import { figureFromElement } from "../export";
import { useElementWidth } from "../hooks/useElementWidth";
import { FIGURE_BACKGROUND } from "../theme";
import type { Series } from "../types";

interface Props {
  label: string;
  color: string;
  a: Series; // the main run
  b?: Series; // a run being compared (drawn dashed)
  lastTick: number;
  droughts: [number, number][];
  cursor: number;
  onPick: (tick: number) => void; // click or drag on the chart
  markers?: { tick: number; label: string }[]; // e.g. milestones, drawn as small ticks
  height?: number;
  exportAs?: { stem: string; description: string }; // shows an export button when given
}

const PAD = { left: 36, right: 6, top: 18, bottom: 4 };

/** One small chart of a metric over the whole run, with drought bands and the cursor. */
export function LineChart(props: Props) {
  const { label, color, a, b, lastTick, droughts, cursor, onPick, markers, height = 70, exportAs } = props;
  const [ref, width] = useElementWidth<HTMLDivElement>();
  const svgRef = useRef<SVGSVGElement>(null);
  const dragging = useRef(false);
  const gradientId = `fill${useId().replace(/[^a-zA-Z0-9]/g, "")}`;

  const all = [...a, ...(b ?? [])].map(([, v]) => v);
  const low = Math.min(0, ...all);
  const high = Math.max(low + 1e-9, ...all);
  const plotWidth = Math.max(10, width - PAD.left - PAD.right);
  const plotHeight = height - PAD.top - PAD.bottom;
  const x = (tick: number) => PAD.left + (tick / Math.max(1, lastTick)) * plotWidth;
  const y = (value: number) => PAD.top + plotHeight - ((value - low) / (high - low)) * plotHeight;
  const path = (series: Series) =>
    series.map(([tick, v], i) => `${i ? "L" : "M"}${x(tick).toFixed(1)},${y(v).toFixed(1)}`).join("");
  // The area under the main line, closed along the bottom of the plot.
  const area = a.length
    ? `${path(a)}L${x(a[a.length - 1][0]).toFixed(1)},${PAD.top + plotHeight}L${x(a[0][0]).toFixed(1)},${PAD.top + plotHeight}Z`
    : "";

  const valueAt = (series: Series | undefined) => {
    if (!series?.length) return null;
    let found: number | null = null;
    for (const [tick, v] of series) {
      if (tick > cursor) break;
      found = v;
    }
    return found;
  };
  const current = valueAt(a);
  const compared = valueAt(b);

  const pick = (event: React.MouseEvent<SVGSVGElement>) => {
    const box = event.currentTarget.getBoundingClientRect();
    const tick = ((event.clientX - box.left - PAD.left) / plotWidth) * lastTick;
    onPick(Math.max(0, Math.min(lastTick, Math.round(tick))));
  };

  const csvRows = () => {
    const bByTick = new Map(b ?? []);
    return [["tick", label, ...(b ? [`${label} (compared run)`] : [])], ...a.map(([t, v]) => [t, v, ...(b ? [bByTick.get(t) ?? null] : [])])];
  };

  return (
    <div className="line-chart" ref={ref}>
      {exportAs && (
        <ExportMenu
          stem={exportAs.stem}
          title={label}
          description={exportAs.description}
          figure={() => (svgRef.current ? figureFromElement(svgRef.current, FIGURE_BACKGROUND) : null)}
          rows={csvRows}
        />
      )}
      {width > 0 && (
        <svg
          ref={svgRef}
          width={width}
          height={height}
          onMouseDown={(e) => {
            dragging.current = true;
            pick(e);
          }}
          onMouseMove={(e) => dragging.current && pick(e)}
          onMouseUp={() => (dragging.current = false)}
          onMouseLeave={() => (dragging.current = false)}
        >
          <defs>
            <linearGradient id={gradientId} x1="0" x2="0" y1="0" y2="1">
              <stop offset="0" stopColor={color} stopOpacity={0.22} />
              <stop offset="1" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          {droughts.map(([start, end]) => (
            <g key={start}>
              <rect
                className="drought-band"
                x={x(start)}
                y={PAD.top}
                width={Math.max(1, x(end) - x(start))}
                height={plotHeight}
              />
              <rect className="drought-edge" x={x(start)} y={PAD.top} width={Math.max(1, x(end) - x(start))} height={2} />
            </g>
          ))}
          <line className="chart-grid" x1={PAD.left} x2={PAD.left + plotWidth} y1={PAD.top + plotHeight / 2} y2={PAD.top + plotHeight / 2} />
          <line className="chart-grid" x1={PAD.left} x2={PAD.left + plotWidth} y1={PAD.top + plotHeight} y2={PAD.top + plotHeight} />
          <text className="chart-label" x={PAD.left} y={12}>
            {label}
            <tspan className="chart-value" fill={color}>
              {current !== null ? `  ${format(current)}` : ""}
            </tspan>
            {compared !== null && <tspan className="chart-value compare">{`  vs ${format(compared)}`}</tspan>}
          </text>
          <text className="chart-axis" x={PAD.left - 6} y={PAD.top + 7} textAnchor="end">
            {format(high)}
          </text>
          <text className="chart-axis" x={PAD.left - 6} y={PAD.top + plotHeight} textAnchor="end">
            {format(low)}
          </text>
          <path d={area} fill={`url(#${gradientId})`} stroke="none" />
          {b && <path d={path(b)} fill="none" stroke={color} strokeWidth={1.2} strokeDasharray="4 3" opacity={0.6} />}
          <path d={path(a)} fill="none" stroke={color} strokeWidth={1.5} strokeLinejoin="round" />
          {markers?.map((m, i) => (
            <line key={i} className="marker" x1={x(m.tick)} x2={x(m.tick)} y1={PAD.top} y2={PAD.top + 6}>
              <title>{`tick ${m.tick}: ${m.label}`}</title>
            </line>
          ))}
          <line className="cursor-line" x1={x(cursor)} x2={x(cursor)} y1={PAD.top} y2={PAD.top + plotHeight} />
        </svg>
      )}
    </div>
  );
}

function format(value: number): string {
  if (Math.abs(value) >= 100) return value.toFixed(0);
  if (Math.abs(value) >= 10) return value.toFixed(1);
  return value.toFixed(2);
}
