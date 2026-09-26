import { useEffect, useState } from "react";
import { api } from "./api";
import type { TrailNode } from "./types";

interface Props {
  runId: number;
  eventId: number;
  onJump: (tick: number, subject: string | null) => void;
}

/** "Why did this happen?": the event, the events that led to it, and so on backwards.
 * Recorded causes are contributing causes the rules knew about, not proof; for proof, compare
 * runs with and without a mechanism (the Experiments tab). */
export function CausalTrail({ runId, eventId, onJump }: Props) {
  const [root, setRoot] = useState<TrailNode | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setRoot(null);
    api.trail(runId, eventId, 3).then(setRoot, (e) => setError(String(e)));
  }, [runId, eventId]);

  async function expand(node: TrailNode) {
    const deeper = await api.trail(runId, node.id, 3);
    setRoot((current) => (current ? replace(current, node.id, deeper) : current));
  }

  return (
    <div className="trail">
      <div className="page-title">
        <h2>Why did this happen?</h2>
        <p className="small">
          Each step lists what the simulation recorded as contributing to the step above it. To test whether a cause
          really matters, compare runs with and without that mechanism.
        </p>
      </div>
      <section className="panel-section">
        {error && <div className="error">{error}</div>}
        {!root && !error && <div className="faint">Loading…</div>}
        {root && (
          <ol className="trail-tree">
            <TrailItem node={root} onExpand={expand} onJump={onJump} />
          </ol>
        )}
      </section>
    </div>
  );
}

function TrailItem({
  node,
  onExpand,
  onJump,
}: {
  node: TrailNode;
  onExpand: (node: TrailNode) => void;
  onJump: (tick: number, subject: string | null) => void;
}) {
  if (node.missing) {
    return <li className="faint small">(a routine event not stored in this summary run)</li>;
  }
  const hasCauses = (node.caused_by?.length ?? 0) > 0;
  return (
    <li>
      <button
        className="trail-node"
        onClick={() => onJump(node.tick ?? 0, node.subjects?.[0] ?? null)}
        title="go to this tick"
      >
        <span className="meta">
          tick {node.tick} <span className="kind-badge">{node.kind}</span>
        </span>
        <span>{node.message}</span>
        {node.cause && <span className="cause small">{node.cause}</span>}
      </button>
      {hasCauses && node.causes === null && (
        <button className="link why trail-more" onClick={() => onExpand(node)}>
          why? ({node.caused_by?.length} more)
        </button>
      )}
      {node.causes && node.causes.length > 0 && (
        <ol>
          {node.causes.map((cause) => (
            <TrailItem key={cause.id} node={cause} onExpand={onExpand} onJump={onJump} />
          ))}
        </ol>
      )}
    </li>
  );
}

function replace(tree: TrailNode, id: number, replacement: TrailNode): TrailNode {
  if (tree.id === id) return replacement;
  if (!tree.causes) return tree;
  return { ...tree, causes: tree.causes.map((c) => replace(c, id, replacement)) };
}
