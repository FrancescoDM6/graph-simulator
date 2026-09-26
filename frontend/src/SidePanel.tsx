import type { ReactNode } from "react";
import { BackIcon } from "./icons";

export type SideTab = "inspect" | "events" | "communities" | "branches";

const TABS: [SideTab, string][] = [
  ["inspect", "Inspect"],
  ["events", "Events"],
  ["communities", "Communities"],
  ["branches", "Branches"],
];

interface Props {
  tab: SideTab;
  onTab: (tab: SideTab) => void;
  content: Record<SideTab, ReactNode>;
  // A page opened on top of the tabs (a community page, a causal trail), with a way back.
  page: { content: ReactNode; backLabel: string; onBack: () => void } | null;
}

/** The right-hand panel: tabs for the selected node, the event feed and communities, and pages
 * that open on top of them. */
export function SidePanel({ tab, onTab, content, page }: Props) {
  return (
    <aside className="side-panel">
      {page ? (
        <div className="side-back">
          <button className="ghost small" onClick={page.onBack}>
            <BackIcon /> {page.backLabel}
          </button>
        </div>
      ) : (
        <div className="side-tabs">
          <nav className="segmented">
            {TABS.map(([id, label]) => (
              <button key={id} className={tab === id ? "active" : ""} onClick={() => onTab(id)}>
                {label}
              </button>
            ))}
          </nav>
        </div>
      )}
      {/* Events and communities manage their own scrolling (a fixed header over a list). */}
      <div className={`side-body ${!page && (tab === "events" || tab === "communities") ? "fill" : ""}`}>
        {page ? page.content : content[tab]}
      </div>
    </aside>
  );
}
