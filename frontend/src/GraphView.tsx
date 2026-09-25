import cytoscape from "cytoscape";
import fcose from "cytoscape-fcose";
import { useEffect, useRef } from "react";
import { edgeData, nodeData, type OccupationColors, stylesheet } from "./graphStyle";
import type { GraphNode, Layer, Snapshot } from "./types";

cytoscape.use(fcose);

// Re-running the force layout on every tick makes the graph jitter, so it runs at most this often.
const LAYOUT_MIN_INTERVAL_MS = 1500;
const LAYOUT_ANIMATION_MS = 700;
const NEW_NODE_JITTER = 40; // new nodes appear next to a neighbour, offset by up to this much
const TOWN_RING_RADIUS = 320; // towns start evenly spaced on a circle this big

// How long each kind of edge "wants" to be. Shorter = pulls its nodes closer together.
const IDEAL_EDGE_LENGTH: Record<Layer, number> = { social: 70, trade: 90, membership: 60, access: 130 };

interface Props {
  snapshot: Snapshot;
  colors: OccupationColors;
  visibleLayers: Set<Layer>;
  selectedId: string | null;
  highlight: Set<string> | null; // e.g. a community's members; everything else fades
  onSelect: (id: string | null) => void;
}

export function GraphView({ snapshot, colors, visibleLayers, selectedId, highlight, onSelect }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<cytoscape.Core | null>(null);
  const layoutRef = useRef<cytoscape.Layouts | null>(null);
  const lastLayoutAt = useRef(0);
  const pendingLayout = useRef<number | undefined>(undefined);
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;

  // Create the Cytoscape instance once.
  useEffect(() => {
    const cy = cytoscape({ container: containerRef.current, style: stylesheet, minZoom: 0.2, maxZoom: 3 });
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

  // Apply each snapshot, and re-run the layout if nodes or edges appeared or disappeared.
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    const isFirstSnapshot = cy.nodes().length === 0;
    const topologyChanged = syncElements(cy, snapshot, colors);
    if (isFirstSnapshot) {
      placeDeterministically(cy, snapshot);
      runLayout(cy, layoutRef, { first: true });
      lastLayoutAt.current = Date.now();
    } else if (topologyChanged && pendingLayout.current === undefined) {
      const wait = Math.max(0, lastLayoutAt.current + LAYOUT_MIN_INTERVAL_MS - Date.now());
      pendingLayout.current = window.setTimeout(() => {
        pendingLayout.current = undefined;
        lastLayoutAt.current = Date.now();
        runLayout(cy, layoutRef, { first: false });
      }, wait);
    }
  }, [snapshot, colors]);

  // Show only the chosen layers; fade what isn't connected to the selection or highlighted.
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
        cy.elements().difference(selected.closedNeighborhood()).addClass("faded");
      } else if (highlight) {
        const members = cy.nodes().filter((n) => highlight.has(n.id()));
        cy.elements().difference(members.union(members.edgesWith(members))).addClass("faded");
      }
    });
  }, [snapshot, visibleLayers, selectedId, highlight]);

  return <div className="graph" ref={containerRef} />;
}

/** Adds, updates and removes elements to match the snapshot. Returns true if topology changed. */
function syncElements(cy: cytoscape.Core, snapshot: Snapshot, colors: OccupationColors): boolean {
  const wantedNodes = new Map(snapshot.nodes.map((n) => [n.id, n]));
  const wantedEdges = new Map(snapshot.edges.map((e) => [e.id, e]));
  let changed = false;

  cy.batch(() => {
    const gone = cy.elements().filter((el) => (el.isNode() ? !wantedNodes.has(el.id()) : !wantedEdges.has(el.id())));
    if (gone.nonempty()) {
      gone.remove();
      changed = true;
    }
    for (const node of snapshot.nodes) {
      const existing = cy.getElementById(node.id);
      if (existing.nonempty()) {
        existing.data(nodeData(node, colors));
      } else {
        cy.add({ group: "nodes", data: nodeData(node, colors), position: startingPosition(cy, node, snapshot) });
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

/** A starting layout that depends only on the snapshot, so two panels showing runs with the same
 * seed start out looking the same: towns on a circle, everything else near its town. */
function placeDeterministically(cy: cytoscape.Core, snapshot: Snapshot) {
  const towns = snapshot.nodes.filter((n) => n.kind === "town");
  const townPosition = new Map(
    towns.map((town, i) => {
      const angle = (2 * Math.PI * i) / Math.max(1, towns.length) - Math.PI / 2;
      return [town.id, { x: TOWN_RING_RADIUS * Math.cos(angle), y: TOWN_RING_RADIUS * Math.sin(angle) }];
    }),
  );
  const homeOf = (node: GraphNode): string | undefined => {
    if (node.kind === "agent" || node.kind === "org") return node.home;
    const road = snapshot.edges.find(
      (e) => e.layer === "access" && (e.source === node.id || e.target === node.id),
    );
    return road ? (road.source === node.id ? road.target : road.source) : undefined;
  };
  cy.batch(() => {
    for (const node of snapshot.nodes) {
      const centre = townPosition.get(node.id) ?? townPosition.get(homeOf(node) ?? "") ?? { x: 0, y: 0 };
      if (node.kind === "town") {
        cy.getElementById(node.id).position(centre);
        continue;
      }
      const angle = hash(node.id) * 2 * Math.PI;
      const distance = node.kind === "site" ? 90 : 60 + hash(node.id + "r") * 110;
      cy.getElementById(node.id).position({
        x: centre.x + distance * Math.cos(angle),
        y: centre.y + distance * Math.sin(angle),
      });
    }
  });
}

/** A number in [0, 1) that depends only on the text. */
function hash(text: string): number {
  let h = 2166136261;
  for (let i = 0; i < text.length; i++) h = Math.imul(h ^ text.charCodeAt(i), 16777619);
  return (h >>> 0) / 4294967296;
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
  { first }: { first: boolean },
) {
  layoutRef.current?.stop();
  // After the first placement, towns and sites stay where they are: they are fixed landmarks
  // that stop the whole picture from rotating or drifting as agents rearrange around them.
  const landmarks = first
    ? undefined
    : cy.nodes('[kind = "town"], [kind = "site"]').map((n) => ({ nodeId: n.id(), position: { ...n.position() } }));
  const options = {
    name: "fcose",
    quality: "proof", // required by fcose when starting from existing positions
    randomize: false,
    fixedNodeConstraint: landmarks,
    initialEnergyOnIncremental: 0.1, // incremental layouts only nudge nodes
    fit: first,
    padding: 40,
    animate: !first, // the first placement just appears; later ones glide
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
