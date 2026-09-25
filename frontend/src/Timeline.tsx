import { useRef } from "react";
import { CHART_BACKGROUND, LineChart } from "./charts/LineChart";
import { ExportMenu } from "./ExportMenu";
import { composeFigure, figureFromElement, fileStem, runDescription } from "./export";
import { droughtPeriods } from "./hooks/useRunData";
import type { RunInfo, Series, TimelineSeries } from "./types";

interface Props {
  charts: TimelineSeries[]; // from scenario.toml [viewer.timeline]
  seriesA: Record<string, Series>;
  seriesB: Record<string, Series> | null;
  runA: RunInfo | undefined;
  runB: RunInfo | undefined;
  lastTick: number;
  cursor: number;
  onPick: (tick: number) => void;
}

/** Small multiples of the run's key metrics over time. Click or drag to move the cursor. */
export function Timeline({ charts, seriesA, seriesB, runA, runB, lastTick, cursor, onPick }: Props) {
  const ref = useRef<HTMLElement>(null);
  const droughts = droughtPeriods(seriesA.drought);
  const description =
    runDescription(runA) + (seriesB && runB ? `; dashed: ${runDescription(runB)}` : "") + "; shaded: droughts";

  const wholeTimeline = () => {
    const svgs = [...(ref.current?.querySelectorAll<SVGSVGElement>(".line-chart svg") ?? [])];
    if (svgs.length === 0) return null;
    return composeFigure(
      svgs.map((svg) => figureFromElement(svg, CHART_BACKGROUND)),
      description,
      { background: CHART_BACKGROUND, textColor: "#d7dae0" },
    );
  };
  const allSeries = () => {
    const names = charts.map((c) => c.metric);
    const ticks = [...new Set(names.flatMap((n) => (seriesA[n] ?? []).map(([t]) => t)))].sort((x, y) => x - y);
    const lookup = (series: Record<string, Series>, name: string) => new Map(series[name] ?? []);
    const a = names.map((n) => lookup(seriesA, n));
    const b = seriesB ? names.map((n) => lookup(seriesB, n)) : [];
    return [
      ["tick", ...names, ...(seriesB ? names.map((n) => `${n} (compared)`) : [])],
      ...ticks.map((t) => [t, ...a.map((m) => m.get(t) ?? null), ...b.map((m) => m.get(t) ?? null)]),
    ];
  };

  return (
    <section className="timeline" ref={ref}>
      <div className="timeline-header">
        <span className="muted small">
          {seriesB ? "solid = run on the left, dashed = compared run" : "click or drag a chart to move to that tick"}
        </span>
        <ExportMenu
          stem={fileStem(runA, "timeline")}
          title="Timeline"
          description={description}
          figure={wholeTimeline}
          rows={allSeries}
        />
      </div>
      {charts.map((chart) => (
        <LineChart
          key={chart.metric}
          label={chart.label}
          color={chart.color}
          a={seriesA[chart.metric] ?? []}
          b={seriesB ? (seriesB[chart.metric] ?? []) : undefined}
          lastTick={lastTick}
          droughts={droughts}
          cursor={cursor}
          onPick={onPick}
          exportAs={{ stem: fileStem(runA, chart.metric), description }}
        />
      ))}
    </section>
  );
}
