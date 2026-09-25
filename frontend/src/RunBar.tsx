import { runLabel } from "./format";
import type { RunInfo } from "./types";

export type Tab = "explore" | "experiments";

interface Props {
  runs: RunInfo[]; // full-detail runs the viewer can play
  runA: number | null;
  runB: number | null;
  onSelectA: (id: number | null) => void;
  onSelectB: (id: number | null) => void;
  onNewRun: () => void;
  tab: Tab;
  onTab: (tab: Tab) => void;
}

/** Which run is shown (and which one it is compared with), plus the page tabs. */
export function RunBar({ runs, runA, runB, onSelectA, onSelectB, onNewRun, tab, onTab }: Props) {
  const newestFirst = [...runs].reverse();
  return (
    <header className="run-bar">
      <nav className="tabs">
        <button className={tab === "explore" ? "active" : ""} onClick={() => onTab("explore")}>
          Explore
        </button>
        <button className={tab === "experiments" ? "active" : ""} onClick={() => onTab("experiments")}>
          Experiments
        </button>
      </nav>
      {tab === "explore" && (
        <>
          <label>
            Run{" "}
            <select value={runA ?? ""} onChange={(e) => onSelectA(e.target.value ? Number(e.target.value) : null)}>
              <option value="">choose a run…</option>
              {newestFirst.map((run) => (
                <option key={run.id} value={run.id}>
                  {runLabel(run)}
                </option>
              ))}
            </select>
          </label>
          <label>
            compare with{" "}
            <select value={runB ?? ""} onChange={(e) => onSelectB(e.target.value ? Number(e.target.value) : null)}>
              <option value="">nothing</option>
              {newestFirst
                .filter((run) => run.id !== runA)
                .map((run) => (
                  <option key={run.id} value={run.id}>
                    {runLabel(run)}
                  </option>
                ))}
            </select>
          </label>
          <button className="primary" onClick={onNewRun}>
            New run…
          </button>
        </>
      )}
    </header>
  );
}
