import { useEffect, useState } from "react";
import { api } from "./api";
import { type StripRow, StripPlot } from "./charts/StripPlot";
import type { ExperimentReport, Scenario } from "./types";

interface Props {
  scenario: Scenario;
  onOpenRun: (runId: number) => void; // opens a run in Explore (computing full detail if needed)
}

/** Results of an experiment from scenario.toml: for each phenomenon, the distribution of its
 * measure across seeds per variant, how often it is present, and the change from the baseline
 * paired by seed. Run experiments with `python -m graphsim.experiment <name>`. */
export function Experiments({ scenario, onOpenRun }: Props) {
  const names = Object.keys(scenario.experiments);
  const [name, setName] = useState(names[0] ?? "");
  const [report, setReport] = useState<ExperimentReport | null>(null);
  const [extraMeasure, setExtraMeasure] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!name) return;
    setReport(null);
    setError("");
    api.experiment(name).then(setReport, (e) => setError(String(e)));
  }, [name]);

  const summary = (label: string, measure: string) =>
    report?.summary.find((s) => s.label === label && s.measure === measure);
  const paired = (label: string, measure: string) =>
    report?.paired.find((p) => p.label === label && p.measure === measure);

  const rowsFor = (measure: string, phenomenon?: string): StripRow[] =>
    (report?.labels ?? []).map((label) => {
      const runs = report!.runs.filter((r) => r.label === label && measure in r.measures);
      const presence = phenomenon ? summary(label, `present:${phenomenon}`) : undefined;
      const pair = paired(label, measure);
      const notes = [];
      if (presence) {
        notes.push(`${Math.round((presence.mean ?? 0) * 100)}% [${pct(presence.p5)}–${pct(presence.p95)}]`);
      }
      if (pair?.n && pair.median_diff !== null) {
        notes.push(`${pair.median_diff >= 0 ? "+" : ""}${pair.median_diff.toFixed(2)} (${pct(pair.same_sign)})`);
      }
      return {
        label,
        points: runs.map((r) => ({
          value: r.measures[measure],
          runId: r.run_id,
          seed: r.seed,
          present: phenomenon ? r.present[phenomenon] : undefined,
        })),
        median: summary(label, measure)?.median ?? null,
        note: notes.join("  "),
      };
    });

  const measures = report ? [...new Set(report.runs.flatMap((r) => Object.keys(r.measures)))].sort() : [];
  const spec = scenario.experiments[name];

  return (
    <div className="experiments-page">
      <div className="experiments-inner">
        <div className="experiments-head">
          <h1>Experiment</h1>
          <select value={name} onChange={(e) => setName(e.target.value)} aria-label="experiment">
            {names.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
          {spec && (
            <span className="faint">
              {spec.seeds} seeds × {spec.variants.length} variants × {spec.ticks} ticks
            </span>
          )}
        </div>
        {spec && <p className="experiments-intro">{spec.description}</p>}
        {error && <div className="error">{error}</div>}
        {report && report.runs.length === 0 && (
          <div className="card muted">
            No runs stored yet. Run <code>uv run python -m graphsim.experiment {name}</code> in backend/.
          </div>
        )}
        {report && report.runs.length > 0 && (
          <>
            <p className="experiments-intro small">
              {report.runs.length} runs. Each dot is one seed (click it to open that world); the white tick is the
              median, hollow dots are worlds without the phenomenon. Right: share of worlds showing it [95% interval],
              then the median change from {report.baseline} for the same seed (share of seeds changing that way).
            </p>
            {Object.entries(scenario.phenomena).map(([phenomenon, p]) => (
              <section key={phenomenon} className="card">
                <div className="card-head">
                  <h2>{phenomenon.replace(/_/g, " ")}</h2>
                  <span className="description">{p.description}</span>
                  <span className="threshold-chip">
                    present if {p.measure} {p.present_if}
                  </span>
                </div>
                <StripPlot
                  rows={rowsFor(p.measure, phenomenon)}
                  threshold={Number(p.present_if.split(" ")[1])}
                  onPick={onOpenRun}
                  exportAs={{
                    stem: `experiment_${name}_${phenomenon}`,
                    title: `${phenomenon}: ${p.measure} per variant`,
                    description: `experiment ${name} (${report.runs.length} runs); present if ${p.measure} ${p.present_if}; right: share present [95% CI], median change vs ${report.baseline} for the same seed (share of seeds)`,
                  }}
                />
              </section>
            ))}
            <section className="card">
              <div className="card-head">
                <h2>Any measure</h2>
                <select value={extraMeasure} onChange={(e) => setExtraMeasure(e.target.value)} aria-label="measure">
                  <option value="">choose…</option>
                  {measures.map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </select>
              </div>
              {extraMeasure && (
                <StripPlot
                  rows={rowsFor(extraMeasure)}
                  onPick={onOpenRun}
                  exportAs={{
                    stem: `experiment_${name}_${extraMeasure}`,
                    title: `${extraMeasure} per variant`,
                    description: `experiment ${name} (${report.runs.length} runs); right: median change vs ${report.baseline} for the same seed`,
                  }}
                />
              )}
            </section>
          </>
        )}
      </div>
    </div>
  );
}

function pct(value: number | null | undefined): string {
  return value === null || value === undefined ? "–" : `${Math.round(value * 100)}%`;
}
