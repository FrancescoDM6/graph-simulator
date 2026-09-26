import { useEffect, useState } from "react";
import { api } from "./api";
import { LineChart } from "./charts/LineChart";
import { fileStem, runDescription } from "./export";
import type { CommunityPage, OrgPage, RunInfo, Series } from "./types";

interface Props {
  runId: number;
  run: RunInfo | undefined;
  group: { kind: "community"; id: number } | { kind: "org"; id: string };
  lastTick: number;
  cursor: number;
  droughts: [number, number][];
  name: (id: string) => string;
  onJump: (tick: number) => void;
  onSelect: (id: string) => void;
  onWhy: (eventId: number) => void;
}

/** A community's or organization's life: size and internal ties over time, who joined and
 * left, and what happened to it. Shown in the side panel. */
export function GroupPage({ runId, run, group, lastTick, cursor, droughts, name, onJump, onSelect, onWhy }: Props) {
  const [page, setPage] = useState<CommunityPage | OrgPage | null>(null);

  useEffect(() => {
    setPage(null);
    const load = group.kind === "community" ? api.community(runId, group.id) : api.org(runId, group.id);
    load.then(setPage);
  }, [runId, group.kind, group.id]);

  const title = group.kind === "community" ? `Community ${group.id}` : (page as OrgPage | null)?.name ?? group.id;
  const series = (value: (row: CommunityPage["history"][number]) => number | null | undefined): Series =>
    (page?.history ?? []).flatMap((row) => {
      const v = value(row);
      return v === null || v === undefined ? [] : [[row.tick, v] as [number, number]];
    });
  const exportAs = (what: string) => ({
    stem: fileStem(run, `${group.kind}-${group.id}`, what),
    description: `${title}, ${runDescription(run)}`,
  });
  const chart = (label: string, color: string, data: Series, what: string) => (
    <LineChart
      label={label}
      color={color}
      a={data}
      lastTick={lastTick}
      droughts={droughts}
      cursor={cursor}
      onPick={onJump}
      height={64}
      exportAs={exportAs(what)}
    />
  );

  return (
    <div className="group-page">
      <div className="page-title">
        <div className="label">{group.kind === "community" ? "Community" : "Organization"}</div>
        <h2>{title}</h2>
        {!page && <p>Loading…</p>}
        {page && "record" in page && (
          <p>
            Born tick {page.record.born}
            {page.record.parent !== null && `, split off from community ${page.record.parent}`}.{" "}
            {page.record.died !== null
              ? `Died tick ${page.record.died} (${page.record.fate}${page.record.merged_into !== null ? ` into community ${page.record.merged_into}` : ""}).`
              : "Still alive."}{" "}
            Peak {page.record.peak_size} members, {page.record.members_ever} different members over its life, turnover{" "}
            {(page.record.mean_turnover * 100).toFixed(1)}% per detection.
          </p>
        )}
      </div>
      {page && (
        <section className="panel-section">
          <h3>Over time</h3>
          {page.history.length === 0 && <div className="faint small">No history stored for this run.</div>}
          {page.history.length > 0 && (
            <div className="agent-charts">
              {chart("Members", "#b07aa1", series((r) => r.size), "size")}
              {chart("Internal density", "#76b7b2", series((r) => r.density), "density")}
              {chart("Mean trust between members", "#6ea8fe", series((r) => r.trust), "trust")}
              {group.kind === "community" && chart("Trade between members", "#f0a04b", series((r) => r.trade), "trade")}
            </div>
          )}
        </section>
      )}
      {page && page.changes.length > 0 && (
        <section className="panel-section">
          <h3>Joined and left</h3>
          <ul className="rows">
            {page.changes
              .slice(-40)
              .reverse()
              .map((c) => (
                <li key={c.tick}>
                  <button className="tick link" onClick={() => onJump(c.tick)}>
                    {c.tick}
                  </button>
                  <span>
                    {c.joined.length > 0 && (
                      <span className="up">
                        + {c.joined.map((id) => <Name key={id} id={id} name={name} onSelect={onSelect} />)}
                      </span>
                    )}{" "}
                    {c.left.length > 0 && (
                      <span className="down">
                        − {c.left.map((id) => <Name key={id} id={id} name={name} onSelect={onSelect} />)}
                      </span>
                    )}
                  </span>
                </li>
              ))}
          </ul>
        </section>
      )}
      {page && page.events.length > 0 && (
        <section className="panel-section">
          <h3>Events</h3>
          <ul className="rows">
            {page.events.map((e) => (
              <li key={e.id}>
                <button className="tick link" onClick={() => onJump(e.tick)}>
                  {e.tick}
                </button>
                <span>
                  {e.message}
                  {e.caused_by.length > 0 && (
                    <button className="link why" onClick={() => onWhy(e.id)}>
                      why?
                    </button>
                  )}
                </span>
                {e.cause && <span className="cause">{e.cause}</span>}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function Name({ id, name, onSelect }: { id: string; name: (id: string) => string; onSelect: (id: string) => void }) {
  return (
    <>
      <button className="link" onClick={() => onSelect(id)}>
        {name(id)}
      </button>{" "}
    </>
  );
}
