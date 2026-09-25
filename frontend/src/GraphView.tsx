import cytoscape from "cytoscape";
import fcose from "cytoscape-fcose";
import cytoscapeSvg from "cytoscape-svg";
import { type Ref, useEffect, useImperativeHandle, useRef, useState } from "react";
import {
  type Coloring,
  type ColorMode,
  communityColor,
  edgeData,
  edgeId,
  hullPath,
  nodeData,
  numericValue,
  stylesheet,
} from "./graphStyle";
import type { AgentNode, GraphNode, Layer, SimEvent, Snapshot } from "./types";

cytoscape.use(fcose);
cytoscape.use(cytoscapeSvg);

// Re-running the force layout on every tick makes the graph jitter, so it runs at most this often.
const LAYOUT_MIN_INTERVAL_MS = 1500;
const LAYOUT_ANIMATION_MS = 700;
const NEW_NODE_JITTER = 40; // new nodes appear next to a neighbour, offset by up to this much
const TOWN_RING_RADIUS = 320; // towns start evenly spaced on a circle this big
const PULSE_MS = 650; // how long an event highlight stays on
const HULL_PADDING = 12; // space between a community's nodes and its outline

// How long each kind of edge "wants" to be. Shorter = pulls its nodes closer together.
const IDEAL_EDGE_LENGTH: Record<Layer, number> = { social: 70, trade: 90, membership: 60, access: 130 };

export interface GraphExport {
  /** An SVG of the graph (whole graph, or the current view in ego mode) with outlines drawn in. */
  svg: (options: { background: string }) => { svg: string; width: number; height: number };
}

export interface ColoringChoice {
  mode: ColorMode;
  occupationColors: Record<string, string>;
  townColors: Record<string, string>;
}

interface Props {
  snapshot: Snapshot;
  coloring: ColoringChoice;
  visibleLayers: Set<Layer>;
  selectedId: string | null;
  highlight: Set<string> | null; // e.g. a community's members; everything else fades
  pulses: SimEvent[]; // events to flash on the graph (usually: this tick's)
  ego: { id: string; hops: number } | null; // show only this agent's neighbourhood
  showHulls: boolean; // draw an outline around each community
  onSelect: (id: string | null) => void;
  ref?: Ref<GraphExport>;
}

export function GraphView(props: Props) {
  const { snapshot, coloring, visibleLayers, selectedId, highlight, pulses, ego, showHulls, onSelect, ref } = props;
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<cytoscape.Core | null>(null);
  const layoutRef = useRef<cytoscape.Layouts | null>(null);
  const lastLayoutAt = useRef(0);
  const pendingLayout = useRef<number | undefined>(undefined);
  const savedPositions = useRef<Map<string, cytoscape.Position> | null>(null); // before ego view
  const egoMembers = useRef<string>("");
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;
  const [hulls, setHulls] = useState<{ community: number; d: string }[]>([]);
  const [viewport, setViewport] = useState({ x: 0, y: 0, zoom: 1 });

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
    const topologyChanged = syncElements(cy, snapshot, fullColoring(coloring, snapshot));
    if (isFirstSnapshot) {
      placeDeterministically(cy, snapshot);
      runLayout(cy, layoutRef, { first: true });
      lastLayoutAt.current = Date.now();
    } else if (topologyChanged && !ego && pendingLayout.current === undefined) {
      const wait = Math.max(0, lastLayoutAt.current + LAYOUT_MIN_INTERVAL_MS - Date.now());
      pendingLayout.current = window.setTimeout(() => {
        pendingLayout.current = undefined;
        lastLayoutAt.current = Date.now();
        if (!savedPositions.current) runLayout(cy, layoutRef, { first: false });
      }, wait);
    }
  }, [snapshot, coloring, ego]);

  // Show only the chosen layers (and the ego neighbourhood); fade what isn't relevant.
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
        if (!ego) cy.elements().difference(selected.closedNeighborhood()).addClass("faded");
      } else if (highlight) {
        const members = cy.nodes().filter((n) => highlight.has(n.id()));
        cy.elements().difference(members.union(members.edgesWith(members))).addClass("faded");
      }
    });
    applyEgo(cy);
  }, [snapshot, visibleLayers, selectedId, highlight, ego]);

  // Ego view: hide everything beyond `hops` steps from the agent; restore the layout afterwards.
  function applyEgo(cy: cytoscape.Core) {
    if (!ego) {
      if (savedPositions.current) {
        const saved = savedPositions.current;
        savedPositions.current = null;
        egoMembers.current = "";
        cy.elements().removeClass("ego-hidden");
        cy.nodes().forEach((n) => {
          const p = saved.get(n.id());
          if (p) n.position(p);
        });
        cy.fit(undefined, 40);
      }
      return;
    }
    const centre = cy.getElementById(ego.id);
    if (centre.empty()) return;
    if (!savedPositions.current) {
      savedPositions.current = new Map(cy.nodes().map((n) => [n.id(), { ...n.position() }]));
    }
    let members = centre as cytoscape.CollectionReturnValue;
    for (let hop = 0; hop < ego.hops; hop++) {
      const visibleEdges = members.connectedEdges().filter((e) => !e.hasClass("hidden"));
      members = members.union(visibleEdges.connectedNodes());
    }
    const key = members.map((n) => n.id()).sort().join(",");
    cy.elements().addClass("ego-hidden");
    members.union(members.edgesWith(members)).removeClass("ego-hidden");
    if (key === egoMembers.current) return; // same neighbourhood: keep its layout
    egoMembers.current = key;
    const distance = (node: cytoscape.NodeSingular) =>
      node.id() === ego.id ? 0 : centre.edgesWith(node).nonempty() ? 1 : 2;
    members
      .layout({
        name: "concentric",
        concentric: (node: cytoscape.NodeSingular) => 3 - distance(node),
        levelWidth: () => 1,
        minNodeSpacing: 30,
        animate: true,
        animationDuration: 400,
        fit: true,
        padding: 40,
      } as cytoscape.LayoutOptions)
      .run();
  }

  // Flash this tick's events on the elements they involve.
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy || pulses.length === 0) return;
    const touched: [cytoscape.CollectionReturnValue, string][] = [];
    const flash = (ids: string[], className: string) => {
      let elements = cy.collection();
      for (const id of ids) elements = elements.union(cy.getElementById(id));
      elements.addClass(className);
      touched.push([elements, className]);
    };
    for (const event of pulses) {
      const [a, b, c] = event.subjects;
      switch (event.kind) {
        case "trade":
          flash(c ? [edgeId(a, c, "trade"), edgeId(c, b, "trade"), a, b, c] : [edgeId(a, b, "trade"), a, b], "pulse-trade");
          break;
        case "gift":
          flash([a, b], "pulse-gift");
          break;
        case "starving":
          flash([a], "pulse-starving");
          break;
        case "arrived":
          flash([a], "pulse-population");
          break;
        case "left":
          flash([b], "pulse-population"); // the agent is gone; its town flashes
          break;
        case "joined_org":
        case "left_org":
        case "founded_org":
          flash([a, b], "pulse-org");
          break;
        case "trusted":
          flash([edgeId(a, b, "social")], "pulse-trust-up");
          break;
        case "distrusted":
          flash([edgeId(a, b, "social")], "pulse-trust-down");
          break;
      }
    }
    const timer = window.setTimeout(() => touched.forEach(([els, name]) => els.removeClass(name)), PULSE_MS);
    return () => {
      window.clearTimeout(timer);
      touched.forEach(([els, name]) => els.removeClass(name));
    };
  }, [pulses]);

  // Community outlines, in model coordinates; one transform follows pan and zoom.
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy || !showHulls) {
      setHulls([]);
      return;
    }
    // Many events can fire per frame (e.g. during a layout animation): redraw at most every 30 ms.
    let timer: number | undefined;
    const update = () => {
      if (timer !== undefined) return;
      timer = window.setTimeout(() => {
        timer = undefined;
        setHulls(communityHulls(cy));
        setViewport({ ...cy.pan(), zoom: cy.zoom() });
      }, 30);
    };
    const events = "render viewport position add remove data";
    update();
    cy.on(events, update);
    return () => {
      window.clearTimeout(timer);
      cy.off(events, update);
    };
  }, [showHulls]);

  useImperativeHandle(ref, () => ({
    svg: ({ background }) => exportSvg(cyRef.current!, background, showHulls, ego !== null),
  }));

  return (
    <>
      <div className="graph" ref={containerRef} />
      {showHulls && (
        <svg className="hulls">
          <g transform={`translate(${viewport.x},${viewport.y}) scale(${viewport.zoom})`}>
            {hulls.map((hull) => (
              <path key={hull.community} d={hull.d} fill={communityColor(hull.community)} stroke={communityColor(hull.community)} />
            ))}
          </g>
        </svg>
      )}
    </>
  );
}

/** The colouring for this snapshot: numeric modes need the range of values at this tick. */
function fullColoring(choice: ColoringChoice, snapshot: Snapshot): Coloring {
  const values = snapshot.nodes
    .filter((n): n is AgentNode => n.kind === "agent")
    .map((n) => numericValue(n, choice.mode))
    .filter((v): v is number => v !== null);
  const range: [number, number] = values.length ? [Math.min(...values), Math.max(...values)] : [0, 1];
  return { ...choice, range };
}

/** Outlines around each community's visible members. */
function communityHulls(cy: cytoscape.Core): { community: number; d: string }[] {
  const groups = new Map<number, { x: number; y: number; r: number }[]>();
  cy.nodes('[kind = "agent"]').forEach((node) => {
    const community = node.data("community") as number;
    if (community < 0 || node.hasClass("hidden") || node.hasClass("ego-hidden")) return;
    const { x, y } = node.position();
    const circles = groups.get(community) ?? [];
    circles.push({ x, y, r: node.width() / 2 + HULL_PADDING });
    groups.set(community, circles);
  });
  return [...groups].filter(([, circles]) => circles.length >= 2).map(([community, circles]) => ({
    community,
    d: hullPath(circles),
  }));
}

/** The graph as a standalone SVG: Cytoscape's own vector export, with outlines behind it. */
function exportSvg(cy: cytoscape.Core, background: string, withHulls: boolean, viewOnly: boolean) {
  const full = !viewOnly;
  const graph: string = (cy as unknown as { svg: (o: object) => string }).svg({ full, scale: 1, bg: background });
  const box = full ? cy.elements().boundingBox() : null;
  const width = Number(/width="([\d.]+)/.exec(graph)?.[1] ?? cy.width());
  const height = Number(/height="([\d.]+)/.exec(graph)?.[1] ?? cy.height());
  // Outlines use model coordinates; move them the way the export moved the graph.
  const shift = box
    ? `translate(${-box.x1},${-box.y1})`
    : `translate(${cy.pan().x},${cy.pan().y}) scale(${cy.zoom()})`;
  const outlines = withHulls
    ? communityHulls(cy)
        .map((h) => {
          const color = communityColor(h.community);
          return `<path d="${h.d}" fill="${color}" fill-opacity="0.12" stroke="${color}" stroke-opacity="0.6" stroke-width="1.5"/>`;
        })
        .join("")
    : "";
  const inner = graph.replace(/^<\?xml[^>]*>\s*/, "").replace(/<!DOCTYPE[^>]*>\s*/, "");
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}">` +
    `<rect width="100%" height="100%" fill="${background}"/>` +
    `<g transform="${shift}">${outlines}</g>` +
    inner.replace("<svg", '<svg x="0" y="0"') +
    `</svg>`;
  return { svg, width, height };
}

/** Adds, updates and removes elements to match the snapshot. Returns true if topology changed. */
function syncElements(cy: cytoscape.Core, snapshot: Snapshot, coloring: Coloring): boolean {
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
        existing.data(nodeData(node, coloring));
      } else {
        cy.add({ group: "nodes", data: nodeData(node, coloring), position: startingPosition(cy, node, snapshot) });
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
    const road = snapshot.edges.find((e) => e.layer === "access" && (e.source === node.id || e.target === node.id));
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
