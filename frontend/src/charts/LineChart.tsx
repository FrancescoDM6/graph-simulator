import { useRef } from "react";
import { useElementWidth } from "../hooks/useElementWidth";
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
  height?: number;
}

const PAD = { left: 44, right: 8, top: 16, bottom: 4 };

/** One small chart of a metric over the whole run, with drought bands and the cursor. */
export function LineChart({ label, color, a, b, lastTick, droughts, cursor, onPick, height = 70 }: Props) {
  const [ref, width] = useElementWidth<HTMLDivElement>();
  const dragging = useRef(false);

  const all = [...a, ...(b ?? [])].map(([, v]) => v);
  const low = Math.min(0, ...all);
  const high = Math.max(low + 1e-9, ...all);
  const plotWidth = Math.max(10, width - PAD.left - PAD.right);
  const plotHeight = height - PAD.top - PAD.bottom;
  const x = (tick: number) => PAD.left + (tick / Math.max(1, lastTick)) * plotWidth;
  const y = (value: number) => PAD.top + plotHeight - ((value - low) / (high - low)) * plotHeight;
  const path = (series: Series) =>
    series.map(([tick, v], i) => `${i ? "L" : "M"}${x(tick).toFixed(1)},${y(v).toFixed(1)}`).join("");

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

  return (
    <div className="line-chart" ref={ref}>
      {width > 0 && (
        <svg
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
          {droughts.map(([start, end]) => (
            <rect
              key={start}
              className="drought-band"
              x={x(start)}
              y={PAD.top}
              width={Math.max(1, x(end) - x(start))}
              height={plotHeight}
            />
          ))}
          <text className="chart-label" x={PAD.left} y={11}>
            {label}
            <tspan className="chart-value" fill={color}>
              {current !== null ? `  ${format(current)}` : ""}
            </tspan>
            {compared !== null && <tspan className="chart-value compare">{`  vs ${format(compared)}`}</tspan>}
          </text>
          <text className="chart-axis" x={PAD.left - 4} y={PAD.top + 8} textAnchor="end">
            {format(high)}
          </text>
          <text className="chart-axis" x={PAD.left - 4} y={PAD.top + plotHeight} textAnchor="end">
            {format(low)}
          </text>
          {b && <path d={path(b)} fill="none" stroke={color} strokeWidth={1.2} strokeDasharray="4 3" opacity={0.7} />}
          <path d={path(a)} fill="none" stroke={color} strokeWidth={1.5} />
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
