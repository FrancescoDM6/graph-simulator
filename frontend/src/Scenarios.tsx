import { useEffect, useState } from "react";
import { api } from "./api";
import { WorldMap } from "./charts/WorldMap";
import type { ExperimentReport, RunInfo, Scenario, WorldInfo } from "./types";

// The experiment that runs every world with the same seeds (scenario.toml [experiments]).
const TOPOLOGIES = "topologies";
// Measures shown next to the phenomena: [measure, column title, how to show the median].
const EXTRA_MEASURES: [string, string, (v: number) => string][] = [
  ["mean_components", "social groups", (v) => v.toFixed(1)],
  ["min_population_ratio", "lowest population", (v) => `${Math.round(v * 100)}%`],
];

interface Props {
  scenario: Scenario;
  worlds: WorldInfo[];
  runs: RunInfo[]; // full-detail runs, to find each world's latest
  onRun: (world: string) => void; // opens the New run dialog for this world
  onOpenRun: (runId: number) => void;
  onOpenExperiment: (name: string) => void;
}

/** Every world in scenarios/: its map, what it holds, and (once the topologies experiment has
 * run) how often each phenomenon appears in it. */
export function Scenarios({ scenario, worlds, runs, onRun, onOpenRun, onOpenExperiment }: Props) {
  const [report, setReport] = useState<ExperimentReport | null>(null);
  const occupationColors = Object.fromEntries(Object.entries(scenario.occupations).map(([o, spec]) => [o, spec.color]));
  const siteColors = Object.fromEntries(
    Object.values(scenario.occupations)
      .filter((spec) => spec.works_at)
      .map((spec) => [spec.works_at, spec.color]),
  );

  useEffect(() => {
    if (TOPOLOGIES in scenario.experiments) api.experiment(TOPOLOGIES).then(setReport, () => setReport(null));
  }, [scenario]);

  const latest = (world: string) => [...runs].reverse().find((r) => r.scenario === world && r.status !== "failed");

  return (
    <div className="experiments-page scenarios-page">
      <div className="experiments-inner">
        <div className="experiments-head">
          <h1>Scenarios</h1>
          <span className="faint">
            {worlds.length} worlds in scenarios/ · every world has the same people and resources unless its description
            says otherwise
          </span>
        </div>
        <p className="experiments-intro">
          The same rules in differently shaped worlds. Comparing them shows which behaviour comes from the rules and
          which from the map.
        </p>
        <PhenomenaGrid scenario={scenario} worlds={worlds} report={report} onOpen={() => onOpenExperiment(TOPOLOGIES)} />
        <div className="world-grid">
          {worlds.map((world) => {
            const run = latest(world.name);
            const summary = world.summary;
            return (
              <section key={world.name} className="card world-card">
                <div className="card-head">
                  <h2>{world.title}</h2>
                  <code>{world.name}</code>
                </div>
                <p className="muted world-description">{world.description}</p>
                <WorldMap world={world} occupationColors={occupationColors} siteColors={siteColors} />
                <div className="world-facts">
                  <span>{summary.people} people</span>
                  {Object.keys(scenario.occupations).map((o) => (
                    <span key={o}>
                      <span className="dot" style={{ background: occupationColors[o] }} />
                      {summary[`people.${o}`]} {o}s
                    </span>
                  ))}
                  <span>
                    {summary.towns} towns · {summary.roads} roads · diameter {summary.diameter}
                  </span>
                </div>
                {world.generator && (
                  <div className="world-facts faint">
                    generator <code>{String(world.generator.name)}</code>
                    {Object.entries(world.generator)
                      .filter(([key]) => key !== "name")
                      .map(([key, value]) => (
                        <span key={key}>
                          {key} = {String(value)}
                        </span>
                      ))}
                  </div>
                )}
                <div className="world-actions">
                  <button className="primary small" onClick={() => onRun(world.name)}>
                    New run…
                  </button>
                  <button className="small" disabled={!run} onClick={() => run && onOpenRun(run.id)}>
                    {run ? `Open run #${run.id}` : "No runs yet"}
                  </button>
                </div>
              </section>
            );
          })}
        </div>
      </div>
    </div>
  );
}

/** Worlds (rows) by phenomena (columns): the share of seeds showing each phenomenon. */
function PhenomenaGrid({
  scenario,
  worlds,
  report,
  onOpen,
}: {
  scenario: Scenario;
  worlds: WorldInfo[];
  report: ExperimentReport | null;
  onOpen: () => void;
}) {
  if (!report || report.runs.length === 0) {
    return (
      <section className="card">
        <div className="card-head">
          <h2>Phenomena by world</h2>
        </div>
        <p className="muted">
          Run <code>uv run python -m graphsim.experiment {TOPOLOGIES}</code> in backend/ to see how often each phenomenon
          appears in each world.
        </p>
      </section>
    );
  }
  const row = (label: string, measure: string) => report.summary.find((s) => s.label === label && s.measure === measure);
  const labelOf = (world: string) =>
    report.labels.find((label) => label === `${world}/baseline`) ?? report.labels.find((l) => l.startsWith(`${world}/`));
  const shown = worlds.filter((w) => labelOf(w.name));
  const seeds = row(report.labels[0], `present:${Object.keys(scenario.phenomena)[0]}`)?.n ?? 0;

  return (
    <section className="card">
      <div className="card-head">
        <h2>Phenomena by world</h2>
        <span className="description">
          Share of {seeds} seeds showing each phenomenon (from the <code>{TOPOLOGIES}</code> experiment). Hover a cell for
          its 95% interval and median; click to see every seed.
        </span>
      </div>
      <div className="table-scroll">
        <table className="phenomena-grid">
          <thead>
            <tr>
              <th />
              {Object.entries(scenario.phenomena).map(([name, p]) => (
                <th key={name} title={`${p.description} (present if ${p.measure} ${p.present_if})`}>
                  {name.replace(/_/g, " ")}
                </th>
              ))}
              {EXTRA_MEASURES.map(([measure, title]) => (
                <th key={measure} className="extra" title={`median ${measure}`}>
                  {title}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {shown.map((world) => {
              const label = labelOf(world.name)!;
              return (
                <tr key={world.name}>
                  <th>{world.title}</th>
                  {Object.entries(scenario.phenomena).map(([name, p]) => {
                    const presence = row(label, `present:${name}`);
                    const stats = row(label, p.measure);
                    const share = presence?.mean ?? 0;
                    return (
                      <td
                        key={name}
                        onClick={onOpen}
                        style={{ background: `rgba(230, 232, 236, ${(0.03 + 0.2 * share).toFixed(3)})` }}
                        title={
                          presence
                            ? `${Math.round(share * 100)}% of ${presence.n} seeds [95%: ${Math.round((presence.p5 ?? 0) * 100)}–${Math.round((presence.p95 ?? 0) * 100)}%]; median ${p.measure} ${stats?.median?.toFixed(3) ?? "–"}`
                            : "no data"
                        }
                      >
                        {presence ? `${Math.round(share * 100)}%` : "–"}
                      </td>
                    );
                  })}
                  {EXTRA_MEASURES.map(([measure, , show]) => {
                    const median = row(label, measure)?.median;
                    return (
                      <td key={measure} className="extra" onClick={onOpen}>
                        {median === null || median === undefined ? "–" : show(median)}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
