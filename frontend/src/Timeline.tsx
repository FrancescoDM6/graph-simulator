import { LineChart } from "./charts/LineChart";
import { droughtPeriods } from "./hooks/useRunData";
import type { Series, TimelineSeries } from "./types";

interface Props {
  charts: TimelineSeries[]; // from scenario.toml [viewer.timeline]
  seriesA: Record<string, Series>;
  seriesB: Record<string, Series> | null;
  lastTick: number;
  cursor: number;
  onPick: (tick: number) => void;
}

/** Small multiples of the run's key metrics over time. Click or drag to move the cursor. */
export function Timeline({ charts, seriesA, seriesB, lastTick, cursor, onPick }: Props) {
  const droughts = droughtPeriods(seriesA.drought);
  return (
    <section className="timeline">
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
        />
      ))}
      {seriesB && <div className="muted small">solid = run shown on the left, dashed = compared run</div>}
    </section>
  );
}
