import { useEffect, useState } from "react";
import { api } from "../api";
import type { RunInfo, Series } from "../types";

const REFRESH_MS = 2000; // how often a still-computing run is re-read

/** A run's info and the metric series the timeline needs, kept fresh while it computes. */
export function useRunData(runId: number | null, metricNames: string[]) {
  const [run, setRun] = useState<RunInfo | null>(null);
  const [series, setSeries] = useState<Record<string, Series>>({});
  const names = metricNames.join(",");

  useEffect(() => {
    setRun(null);
    setSeries({});
    if (runId === null) return;
    let stopped = false;
    let timer: number | undefined;

    async function load() {
      const info = await api.run(runId!);
      const metrics = await api.metrics(runId!, names.split(",").filter(Boolean));
      if (stopped) return;
      setRun(info);
      setSeries(metrics.series);
      if (info.status === "running") timer = window.setTimeout(load, REFRESH_MS);
    }
    load().catch(() => undefined);
    return () => {
      stopped = true;
      window.clearTimeout(timer);
    };
  }, [runId, names]);

  return { run, series };
}

/** [start, end] tick ranges where the "drought" metric is on. */
export function droughtPeriods(drought: Series | undefined): [number, number][] {
  const periods: [number, number][] = [];
  let start: number | null = null;
  for (const [tick, on] of drought ?? []) {
    if (on && start === null) start = tick;
    if (!on && start !== null) {
      periods.push([start, tick - 1]);
      start = null;
    }
  }
  if (start !== null && drought?.length) periods.push([start, drought[drought.length - 1][0]]);
  return periods;
}
