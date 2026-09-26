import { useRef } from "react";
import { LineChart } from "./charts/LineChart";
import { ExportMenu } from "./ExportMenu";
import { composeFigure, figureFromElement, fileStem, runDescription } from "./export";
import { droughtPeriods } from "./hooks/useRunData";
import { ChevronIcon } from "./icons";
import { FIGURE_BACKGROUND, FIGURE_TEXT } from "./theme";
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
  summary: React.ReactNode; // the numbers at the cursor, shown in the header
  open: boolean;
  onToggle: () => void;
}

/** The bottom of the page: numbers at the cursor, and small multiples of the run's key metrics
 * over time (click or drag one to move the cursor). Collapses to just the numbers. */
export function Timeline(props: Props) {
  const { charts, seriesA, seriesB, runA, runB, lastTick, cursor, onPick, summary, open, onToggle } = props;
  const ref = useRef<HTMLDivElement>(null);
  const droughts = droughtPeriods(seriesA.drought);
  const description =
    runDescription(runA) + (seriesB && runB ? `; dashed: ${runDescription(runB)}` : "") + "; shaded: droughts";

  const wholeTimeline = () => {
    const svgs = [...(ref.current?.querySelectorAll<SVGSVGElement>(".line-chart > svg") ?? [])];
    if (svgs.length === 0) return null;
    return composeFigure(
      svgs.map((svg) => figureFromElement(svg, FIGURE_BACKGROUND)),
      description,
      { background: FIGURE_BACKGROUND, textColor: FIGURE_TEXT },
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
    <section className="bottom">
      <div className="bottom-header">
        {summary}
        {open && seriesB && <span className="timeline-note">dashed = compared run</span>}
        {open && (
          <ExportMenu
            stem={fileStem(runA, "timeline")}
            title="Timeline"
            description={description}
            figure={wholeTimeline}
            rows={allSeries}
          />
        )}
        <button className="ghost small" onClick={onToggle} title={open ? "hide the charts" : "show the charts"}>
          Charts <ChevronIcon up={!open} />
        </button>
      </div>
      {open && (
        <div className="timeline-grid" ref={ref}>
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
              height={64}
              exportAs={{ stem: fileStem(runA, chart.metric), description }}
            />
          ))}
        </div>
      )}
    </section>
  );
}
