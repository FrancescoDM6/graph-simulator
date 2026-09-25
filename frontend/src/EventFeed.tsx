import { useState } from "react";
import type { SimEvent } from "./types";

// Events about the network as a whole, rather than one relationship.
const STRUCTURAL_KINDS = new Set([
  "community_formed",
  "community_dissolved",
  "network_split",
  "network_merged",
  "inequality_rising",
  "new_top_broker",
  "drought_started",
  "drought_ended",
  "price_rose",
  "price_fell",
  "founded_org",
  "org_dissolved",
]);

interface Props {
  events: SimEvent[]; // newest first
  liveIds: Set<string>; // nodes currently in the world (others can't be selected)
  onSelect: (id: string) => void;
}

export function EventFeed({ events, liveIds, onSelect }: Props) {
  const [structuralOnly, setStructuralOnly] = useState(false);
  const shown = structuralOnly ? events.filter((e) => STRUCTURAL_KINDS.has(e.kind)) : events;

  return (
    <section className="event-feed">
      <div className="panel-header">
        <span>Events</span>
        <label>
          <input
            type="checkbox"
            checked={structuralOnly}
            onChange={(e) => setStructuralOnly(e.target.checked)}
          />{" "}
          network-level only
        </label>
      </div>
      <ol className="event-list">
        {shown.map((event, i) => {
          const target = event.subjects.find((id) => liveIds.has(id));
          return (
            <li
              key={`${event.tick}-${i}`}
              className={`event ${STRUCTURAL_KINDS.has(event.kind) ? "structural" : ""} ${target ? "clickable" : ""}`}
              onClick={() => target && onSelect(target)}
            >
              <span className="event-tick">{event.tick}</span>
              <span className="event-message">{event.message}</span>
              {event.cause && <span className="event-cause">{event.cause}</span>}
            </li>
          );
        })}
        {shown.length === 0 && <li className="muted">Nothing yet.</li>}
      </ol>
    </section>
  );
}
