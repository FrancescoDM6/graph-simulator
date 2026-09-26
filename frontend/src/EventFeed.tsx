import { useEffect, useState } from "react";
import { api } from "./api";
import type { SimEvent } from "./types";

const WINDOW = 100; // show events from this many ticks before the cursor up to it
const REFETCH_DELAY_MS = 250; // wait for the cursor to settle before fetching

// Events about the network as a whole, rather than one relationship.
const STRUCTURAL_KINDS = new Set([
  "community_formed", "community_split", "community_merged", "community_dissolved",
  "network_split", "network_merged", "inequality_rising", "new_top_broker",
  "drought_started", "drought_ended", "price_rose", "price_fell", "founded_org", "org_dissolved",
  "intervention",
]);

interface Props {
  runId: number;
  cursor: number;
  liveIds: Set<string>; // nodes present at the cursor (others can't be selected)
  onSelect: (id: string) => void;
  onJump: (tick: number) => void;
  onWhy: (eventId: number) => void;
}

/** The events leading up to the cursor, newest first. */
export function EventFeed({ runId, cursor, liveIds, onSelect, onJump, onWhy }: Props) {
  const [events, setEvents] = useState<SimEvent[] | null>(null); // null until the first fetch
  const [structuralOnly, setStructuralOnly] = useState(false);
  const [withDetail, setWithDetail] = useState(false);

  useEffect(() => {
    let stale = false;
    const timer = window.setTimeout(() => {
      api
        .events(runId, { first: Math.max(0, cursor - WINDOW), last: cursor, detail: withDetail, limit: 2000 })
        .then((found) => !stale && setEvents(found.reverse()));
    }, REFETCH_DELAY_MS);
    return () => {
      stale = true;
      window.clearTimeout(timer);
    };
  }, [runId, cursor, withDetail]);

  const shown = (structuralOnly ? events?.filter((e) => STRUCTURAL_KINDS.has(e.kind)) : events) ?? [];
  return (
    <section className="feed">
      <div className="panel-toolbar">
        <span className="num">
          Ticks {Math.max(0, cursor - WINDOW)}–{cursor}
        </span>
        <span className="options">
          <label className="check">
            <input type="checkbox" checked={structuralOnly} onChange={(e) => setStructuralOnly(e.target.checked)} />
            network-level only
          </label>
          <label className="check">
            <input type="checkbox" checked={withDetail} onChange={(e) => setWithDetail(e.target.checked)} />
            every trade attempt
          </label>
        </span>
      </div>
      <ol className="event-list">
        {shown.map((event) => {
          const target = event.subjects.find((id) => liveIds.has(id));
          return (
            <li
              key={event.id}
              className={[
                "event",
                STRUCTURAL_KINDS.has(event.kind) ? "structural" : "",
                event.detail ? "detail" : "",
                event.tick === cursor ? "now" : "",
              ].join(" ")}
            >
              <button className="tick link" onClick={() => onJump(event.tick)} title="go to this tick">
                {event.tick}
              </button>
              <span>
                <span
                  className={`event-message ${target ? "clickable" : ""}`}
                  onClick={() => target && onSelect(target)}
                >
                  {event.message}
                </span>
                {event.caused_by.length > 0 && (
                  <button className="link why" onClick={() => onWhy(event.id)}>
                    why?
                  </button>
                )}
              </span>
              {event.cause && <span className="cause">{event.cause}</span>}
            </li>
          );
        })}
        {events === null && <li className="empty-state">Loading…</li>}
        {events !== null && shown.length === 0 && (
          <li className="empty-state">Nothing happened in the last {WINDOW} ticks.</li>
        )}
      </ol>
    </section>
  );
}
