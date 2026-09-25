import cytoscape from "cytoscape";
import fcose from "cytoscape-fcose";
import { useEffect, useRef } from "react";
import { edgeData, nodeData, stylesheet } from "./graphStyle";
import type { GraphNode, Layer, Snapshot } from "./types";

cytoscape.use(fcose);

// Re-running the force layout every tick makes the graph jitter, so it runs at most this often.
const LAYOUT_MIN_INTERVAL_MS = 1500;
const LAYOUT_ANIMATION_MS = 700;
const NEW_NODE_JITTER = 40; // new nodes appear next to a neighbour, offset by up to this much

// How long each kind of edge "wants" to be. Shorter = pulls its nodes closer together.
const IDEAL_EDGE_LENGTH: Record<Layer, number> = { social: 70, trade: 90, membership: 60, access: 130 };

interface Props {
  snapshot: Snapshot;
  visibleLayers: Set<Layer>;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
}

export function GraphView({ snapshot, visibleLayers, selectedId, onSelect }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<cytoscape.Core | null>(null);
  const layoutRef = useRef<cytoscape.Layouts | null>(null);
  const lastLayoutAt = useRef(0);
  const pendingLayout = useRef<number | undefined>(undefined);
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;

  // Create the Cytoscape instance once.
  useEffect(() => {
    const cy = cytoscape({
      container: containerRef.current,
      style: stylesheet,
      minZoom: 0.2,
      maxZoom: 3,
    });
    cy.on("tap", "node", (event) => onSelectRef.current(event.target.id()));
    cy.on("tap", (event) => {
      if (event.target === cy) onSelectRef.current(null);
    });
    cyRef.current = cy;
    return () => {
      window.clearTimeout(pendingLayout.current);
      cy.destroy();
    };
  }, []);

  // Apply each new snapshot, and re-run the layout if nodes or edges appeared or disappeared.
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    const isFirstSnapshot = cy.nodes().length === 0;
    const topologyChanged = syncElements(cy, snapshot);
    if (isFirstSnapshot) {
      runLayout(cy, layoutRef, { randomize: true, fit: true });
      lastLayoutAt.current = Date.now();
    } else if (topologyChanged) {
      scheduleLayout();
    }

    function scheduleLayout() {
      if (pendingLayout.current !== undefined) return; // one is already queued
      const wait = Math.max(0, lastLayoutAt.current + LAYOUT_MIN_INTERVAL_MS - Date.now());
      pendingLayout.current = window.setTimeout(() => {
        pendingLayout.current = undefined;
        lastLayoutAt.current = Date.now();
        runLayout(cy!, layoutRef, { randomize: false, fit: false });
      }, wait);
    }
  }, [snapshot]);

  // Show only the chosen layers, and fade everything not connected to the selected node.
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.batch(() => {
      cy.edges().forEach((edge) => {
        edge.toggleClass("hidden", !visibleLayers.has(edge.data("layer")));
      });
      cy.nodes('[kind = "town"], [kind = "site"]').toggleClass("hidden", !visibleLayers.has("access"));
      cy.nodes('[kind = "org"]').toggleClass("hidden", !visibleLayers.has("membership"));

      cy.elements().unselect().removeClass("faded");
      const selected = selectedId ? cy.getElementById(selectedId) : null;
      if (selected && selected.nonempty()) {
        selected.select();
        const neighbourhood = selected.closedNeighborhood();
        cy.elements().difference(neighbourhood).addClass("faded");
      }
    });
  }, [snapshot, visibleLayers, selectedId]);

  return <div className="graph" ref={containerRef} />;
}

/** Adds, updates and removes elements to match the snapshot. Returns true if topology changed. */
function syncElements(cy: cytoscape.Core, snapshot: Snapshot): boolean {
  const wantedNodes = new Map(snapshot.nodes.map((n) => [n.id, n]));
  const wantedEdges = new Map(snapshot.edges.map((e) => [e.id, e]));
  let changed = false;

  cy.batch(() => {
    const gone = cy.elements().filter((el) =>
      el.isNode() ? !wantedNodes.has(el.id()) : !wantedEdges.has(el.id()),
    );
    if (gone.nonempty()) {
      gone.remove();
      changed = true;
    }

    for (const node of snapshot.nodes) {
      const existing = cy.getElementById(node.id);
      if (existing.nonempty()) {
        existing.data(nodeData(node));
      } else {
        cy.add({ group: "nodes", data: nodeData(node), position: startingPosition(cy, node, snapshot) });
        changed = true;
      }
    }

    for (const edge of snapshot.edges) {
      const existing = cy.getElementById(edge.id);
      if (existing.nonempty()) {
        existing.data(edgeData(edge, snapshot.tick));
      } else {
        cy.add({ group: "edges", data: edgeData(edge, snapshot.tick) });
        changed = true;
      }
    }
  });
  return changed;
}

/** New nodes start next to a neighbour that's already on screen, so they don't fly in from 0,0. */
function startingPosition(cy: cytoscape.Core, node: GraphNode, snapshot: Snapshot) {
  const jitter = () => (Math.random() - 0.5) * 2 * NEW_NODE_JITTER;
  for (const edge of snapshot.edges) {
    const other = edge.source === node.id ? edge.target : edge.target === node.id ? edge.source : null;
    const neighbour = other ? cy.getElementById(other) : null;
    if (neighbour && neighbour.nonempty()) {
      const p = neighbour.position();
      return { x: p.x + jitter(), y: p.y + jitter() };
    }
  }
  return { x: jitter(), y: jitter() };
}

function runLayout(
  cy: cytoscape.Core,
  layoutRef: React.RefObject<cytoscape.Layouts | null>,
  { randomize, fit }: { randomize: boolean; fit: boolean },
) {
  layoutRef.current?.stop();
  // After the first placement, towns and sites stay where they are: they are fixed landmarks
  // that stop the whole picture from rotating or drifting as agents rearrange around them.
  const landmarks = randomize
    ? undefined
    : cy.nodes('[kind = "town"], [kind = "site"]').map((n) => ({ nodeId: n.id(), position: { ...n.position() } }));
  const options = {
    name: "fcose",
    // fcose requires quality "proof" when starting from the current positions.
    quality: randomize ? "default" : "proof",
    randomize,
    fixedNodeConstraint: landmarks,
    initialEnergyOnIncremental: 0.1, // incremental layouts only nudge nodes
    fit,
    padding: 40,
    // Only incremental updates are animated; the first placement just appears.
    animate: !randomize,
    animationDuration: LAYOUT_ANIMATION_MS,
    nodeRepulsion: 6000,
    gravity: 0.3,
    idealEdgeLength: (edge: cytoscape.EdgeSingular) => IDEAL_EDGE_LENGTH[edge.data("layer") as Layer],
    // Strong social ties pull harder, so close-knit groups visibly cluster.
    edgeElasticity: (edge: cytoscape.EdgeSingular) =>
      edge.data("layer") === "social" ? 0.2 + 0.5 * edge.data("strength") : 0.45,
  } as unknown as cytoscape.LayoutOptions;
  const layout = cy.layout(options);
  layoutRef.current = layout;
  layout.run();
}
