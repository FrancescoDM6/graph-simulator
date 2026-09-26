import { describeIntervention, runLabel } from "./format";
import type { Lineage, RunInfo } from "./types";

// The numbers compared between a run and its branches (at each one's last stored tick).
const FINALS: [string, string, number][] = [
  ["population", "people", 0],
  ["gini_coin", "Gini", 2],
  ["broker_share", "brokers", 2],
  ["avg_trust", "trust", 2],
  ["starving", "starving", 0],
];

interface Props {
  lineage: Lineage | null;
  onOpen: (runId: number) => void;
  onCompare: (runId: number) => void;
}

/** A run's family tree: what it branched from, and its alternate histories, with how each
 * one ended compared with this run. */
export function Branches({ lineage, onOpen, onCompare }: Props) {
  if (!lineage) return <div className="empty-state">Loading…</div>;
  const { run, ancestors, siblings, children } = lineage;

  const row = (other: RunInfo & { final: Record<string, number> }, compareWith = run) => (
    <li key={other.id} className="branch-row">
      <div className="branch-head">
        <span>
          <b>#{other.id}</b>
          {other.branch_tick !== null && <span className="faint"> @ tick {other.branch_tick}</span>}
        </span>
        <span className="branch-actions">
          <button className="ghost small" onClick={() => onCompare(other.id)}>
            Compare
          </button>
          <button className="ghost small" onClick={() => onOpen(other.id)}>
            Open
          </button>
        </span>
      </div>
      <div className="small muted">
        {other.interventions
          .filter((i) => i.tick === other.branch_tick)
          .map(describeIntervention)
          .join(", ") || (other.parent_run === null ? "the original run" : "no changes")}
        {other.label && ` · ${other.label}`}
        {other.status === "running" && ` · computing ${other.ticks_done}/${other.ticks}`}
      </div>
      <div className="finals">
        {FINALS.map(([name, label, digits]) => {
          const value = other.final[name];
          const base = compareWith.final[name];
          const diff = value !== undefined && base !== undefined ? value - base : null;
          return (
            <span key={name} title={`${name} at the last tick`}>
              <span className="faint">{label}</span> {value?.toFixed(digits) ?? "–"}
              {diff !== null && other.id !== compareWith.id && Math.abs(diff) > 10 ** -digits / 2 && (
                <span className={diff > 0 ? "up" : "down"}>
                  {" "}
                  {diff > 0 ? "+" : ""}
                  {diff.toFixed(digits)}
                </span>
              )}
            </span>
          );
        })}
      </div>
    </li>
  );

  return (
    <div className="branches">
      {ancestors.length > 0 && (
        <section className="panel-section">
          <h3>Branched from</h3>
          <ul className="rows plain branch-list">{ancestors.map((a) => row(a, a))}</ul>
          <div className="faint small">This run: {runLabel(run)}</div>
        </section>
      )}
      <section className="panel-section">
        <h3>Branches of this run ({children.length})</h3>
        {children.length === 0 && (
          <div className="faint small">
            None yet. Pause where history should split, press <b>Intervene</b>, choose what changes, and branch.
          </div>
        )}
        <ul className="rows plain branch-list">{children.map((c) => row(c))}</ul>
        {children.length > 0 && <div className="faint small">Differences are against this run at its last tick.</div>}
      </section>
      {siblings.length > 0 && (
        <section className="panel-section">
          <h3>Other branches of #{run.parent_run}</h3>
          <ul className="rows plain branch-list">{siblings.map((s) => row(s))}</ul>
        </section>
      )}
    </div>
  );
}
