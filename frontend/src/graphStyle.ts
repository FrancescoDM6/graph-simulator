// Every visual encoding lives in this file: how simulation state becomes size, colour and shape.
// Occupation colours come from scenario.toml ([occupations.<name>] color).
import type cytoscape from "cytoscape";
import type { AgentNode, GraphEdge, GraphNode, Layer } from "./types";

// Tableau 10: distinguishable categorical colours for communities.
export const COMMUNITY_COLORS = [
  "#4e79a7", "#e15759", "#76b7b2", "#59a14f", "#edc948",
  "#b07aa1", "#ff9da7", "#9c755f", "#f28e2b", "#bab0ac",
];
const NO_COMMUNITY_COLOR = "#4b5260";
const UNKNOWN_OCCUPATION_COLOR = "#999999";
export const STARVING_COLOR = "#f06a6a";
const MEMBERSHIP_COLOR = "#b58df2";
const LABEL_COLOR = "#a3a9b5"; // --text-2 in styles.css
const CANVAS_COLOR = "#0b0d10"; // --bg-0: label outlines blend into the background

export const LAYER_COLORS: Record<Layer, string> = {
  social: "#6ea8fe",
  trade: "#f0a04b",
  membership: MEMBERSHIP_COLOR,
  access: "#6b7280",
};

const RECENT_TRADE_TICKS = 20; // trade edges fade out over this many ticks without a trade

export type OccupationColors = Record<string, string>;

// --- Colouring agents -----------------------------------------------------------------------

export type ColorMode = "community" | "occupation" | "town" | "wealth" | "trust" | "betweenness" | "degree";
export const COLOR_MODES: [ColorMode, string][] = [
  ["community", "community"],
  ["occupation", "occupation"],
  ["town", "home town"],
  ["wealth", "wealth (coin)"],
  ["trust", "mean trust"],
  ["betweenness", "broker score"],
  ["degree", "number of ties"],
];

/** Everything needed to colour agents: the mode, category colours, and for numeric modes the
 * range of values at this tick (lowest value = dark, highest = bright). */
export interface Coloring {
  mode: ColorMode;
  occupationColors: OccupationColors;
  townColors: Record<string, string>;
  range: [number, number];
}

export function communityColor(community: number): string {
  return community < 0 ? NO_COMMUNITY_COLOR : COMMUNITY_COLORS[community % COMMUNITY_COLORS.length];
}

/** The number a numeric colour mode shows, or null for categorical modes / missing values. */
export function numericValue(node: AgentNode, mode: ColorMode): number | null {
  switch (mode) {
    case "wealth":
      return node.coin;
    case "trust":
      return node.mean_trust;
    case "betweenness":
      return node.betweenness;
    case "degree":
      return node.degree;
    default:
      return null;
  }
}

// Viridis: dark purple (low) to yellow (high); readable on the dark background and for most
// kinds of colour blindness.
const SEQUENTIAL = ["#440154", "#3b528b", "#21918c", "#5ec962", "#fde725"];

/** A colour for t in [0, 1] along the sequential scale. */
export function sequentialColor(t: number): string {
  const x = Math.max(0, Math.min(1, t)) * (SEQUENTIAL.length - 1);
  const i = Math.min(Math.floor(x), SEQUENTIAL.length - 2);
  const mix = (a: string, b: string, f: number) =>
    Math.round(parseInt(a, 16) + (parseInt(b, 16) - parseInt(a, 16)) * f)
      .toString(16)
      .padStart(2, "0");
  const [from, to] = [SEQUENTIAL[i], SEQUENTIAL[i + 1]];
  const f = x - i;
  return `#${mix(from.slice(1, 3), to.slice(1, 3), f)}${mix(from.slice(3, 5), to.slice(3, 5), f)}${mix(from.slice(5, 7), to.slice(5, 7), f)}`;
}

function agentFill(node: AgentNode, coloring: Coloring): string {
  switch (coloring.mode) {
    case "community":
      return communityColor(node.community);
    case "occupation":
      return coloring.occupationColors[node.occupation] ?? UNKNOWN_OCCUPATION_COLOR;
    case "town":
      return coloring.townColors[node.home] ?? NO_COMMUNITY_COLOR;
    default: {
      const value = numericValue(node, coloring.mode);
      if (value === null) return NO_COMMUNITY_COLOR;
      const [low, high] = coloring.range;
      return sequentialColor(high > low ? (value - low) / (high - low) : 0.5);
    }
  }
}

/** Data fields the stylesheet below reads, computed from a node's simulation state. */
export function nodeData(node: GraphNode, coloring: Coloring): Record<string, string | number> {
  switch (node.kind) {
    case "agent":
      return {
        id: node.id,
        kind: node.kind,
        label: node.name,
        size: Math.min(46, 12 + 3.2 * Math.sqrt(Math.max(node.coin, 0))), // size = wealth
        fill: agentFill(node, coloring),
        border:
          node.hunger_ticks > 0
            ? STARVING_COLOR
            : (coloring.occupationColors[node.occupation] ?? UNKNOWN_OCCUPATION_COLOR),
        community: node.community,
      };
    case "town":
      return { id: node.id, kind: node.kind, label: node.name, size: 40, fill: "#161a20", border: "#4b5563" };
    case "site":
      return {
        id: node.id,
        kind: node.kind,
        label: node.name,
        size: 18,
        fill: "#1f242c",
        border: node.stock < node.capacity * 0.1 ? STARVING_COLOR : "#4b5563", // red = depleted
      };
    case "org":
      return {
        id: node.id,
        kind: node.kind,
        label: node.name,
        size: Math.min(44, 18 + 2 * node.members),
        fill: MEMBERSHIP_COLOR,
        border: MEMBERSHIP_COLOR,
      };
  }
}

export function edgeData(edge: GraphEdge, tick: number): Record<string, string | number> {
  // Idle ties nearly disappear, so the picture shows what is happening now, not every tie ever.
  let width = 1;
  let opacity = 0.3;
  if (edge.layer === "social") {
    width = 0.8 + 3 * edge.strength;
    opacity = 0.08 + 0.47 * edge.strength;
  } else if (edge.layer === "trade") {
    const recency = Math.max(0, 1 - (tick - edge.last_active) / RECENT_TRADE_TICKS);
    width = 1 + 3 * edge.strength;
    opacity = 0.04 + 0.76 * recency;
  } else if (edge.layer === "membership") {
    opacity = 0.35;
  } else {
    opacity = 0.15;
  }
  return {
    id: edge.id,
    source: edge.source,
    target: edge.target,
    layer: edge.layer,
    strength: edge.strength,
    width,
    opacity,
    color: LAYER_COLORS[edge.layer],
  };
}

// --- Labels ------------------------------------------------------------------------------------
// Which names are readable. Every name at every zoom turns the graph into a wall of text, so
// agents', sites' and organizations' names appear only once zoomed in far enough that they'd be
// drawn at least this big on screen; hovering or selecting a node shows its name (and its
// neighbours') at any zoom. Towns are the landmarks: their names always show.
const LABEL_FONT_SIZE = 10;
const LABEL_MIN_SCREEN_SIZE = 9; // hide names drawn smaller than this (px), i.e. zoom < 0.9

export const stylesheet: cytoscape.StylesheetJson = [
  {
    selector: "node",
    style: {
      width: "data(size)",
      height: "data(size)",
      "background-color": "data(fill)",
      "border-color": "data(border)",
      "border-width": 2,
      // A soft glow in the node's own colour.
      "underlay-color": "data(fill)",
      "underlay-opacity": 0.18,
      "underlay-padding": 5,
      "underlay-shape": "ellipse",
      label: "data(label)",
      color: LABEL_COLOR,
      "font-size": LABEL_FONT_SIZE,
      "min-zoomed-font-size": LABEL_MIN_SCREEN_SIZE,
      "text-valign": "bottom",
      "text-margin-y": 4,
      "text-outline-color": CANVAS_COLOR,
      "text-outline-width": 2,
      "overlay-opacity": 0,
      // Only sizes animate: colours change instantly, so an exported figure never catches a
      // colour half-way through a transition.
      "transition-property": "width, height",
      "transition-duration": 300,
    },
  },
  {
    selector: 'node[kind = "town"]',
    style: {
      shape: "round-rectangle",
      "border-width": 1.5,
      "underlay-opacity": 0,
      color: "#e6e8ec",
      "font-size": 12,
      "font-weight": "bold",
      "min-zoomed-font-size": 0,
    },
  },
  { selector: 'node[kind = "site"]', style: { shape: "diamond", "border-width": 1.5, "underlay-opacity": 0 } },
  {
    selector: 'node[kind = "org"]',
    style: { shape: "hexagon", "background-opacity": 0.22, "border-width": 1.5, "underlay-opacity": 0, "font-style": "italic" },
  },
  // Agents who can't eat glow red.
  { selector: `node[border = "${STARVING_COLOR}"]`, style: { "underlay-color": STARVING_COLOR, "underlay-opacity": 0.35 } },
  {
    selector: "edge",
    style: {
      width: "data(width)",
      "line-color": "data(color)",
      opacity: "data(opacity)" as unknown as number,
      "curve-style": "haystack", // cheap straight lines; parallel layers overlap
      "transition-property": "opacity, width",
      "transition-duration": 300,
    },
  },
  { selector: 'edge[layer = "membership"]', style: { "line-style": "dashed", "line-dash-pattern": [4, 4] } },
  { selector: 'edge[layer = "access"]', style: { "line-style": "dotted" } },
  { selector: ".hidden", style: { visibility: "hidden", events: "no" } },
  { selector: ".ego-hidden", style: { display: "none" } }, // outside the ego neighbourhood
  // Event pulses (see PULSE_KINDS): a brief glow on the elements an event involved.
  { selector: "node.pulse-trade", style: { "underlay-color": "#ffd166", "underlay-opacity": 0.55, "underlay-padding": 9 } },
  { selector: "edge.pulse-trade", style: { "line-color": "#ffd166", opacity: 1, width: 4 } },
  { selector: ".pulse-gift", style: { "underlay-color": "#6fcf8e", "underlay-opacity": 0.6, "underlay-padding": 12 } },
  { selector: ".pulse-starving", style: { "underlay-color": STARVING_COLOR, "underlay-opacity": 0.65, "underlay-padding": 12 } },
  { selector: ".pulse-population", style: { "underlay-color": "#ffffff", "underlay-opacity": 0.4, "underlay-padding": 12 } },
  { selector: ".pulse-org", style: { "underlay-color": MEMBERSHIP_COLOR, "underlay-opacity": 0.6, "underlay-padding": 12 } },
  { selector: "edge.pulse-trust-up", style: { "line-color": "#6fcf8e", opacity: 1, width: 4 } },
  { selector: "edge.pulse-trust-down", style: { "line-color": STARVING_COLOR, opacity: 1, width: 4 } },
  { selector: ".faded", style: { opacity: 0.1 } }, // not part of the selection or highlighted group
  { selector: ".dim", style: { opacity: 0.15 } }, // not next to the hovered node
  { selector: "node.show-label", style: { "min-zoomed-font-size": 0, color: "#e6e8ec" } },
  {
    selector: "node:selected",
    style: {
      "border-width": 3,
      "border-color": "#ffffff",
      "underlay-opacity": 0.35,
      "min-zoomed-font-size": 0,
      color: "#ffffff",
      "font-weight": "bold",
    },
  },
];

// --- Event pulses ----------------------------------------------------------------------------

export type PulseGroup = "trades" | "gifts" | "starving" | "population" | "organizations" | "trust";
export const PULSE_GROUPS: [PulseGroup, string][] = [
  ["trades", "trades"],
  ["gifts", "gifts"],
  ["starving", "starving"],
  ["population", "arrivals & departures"],
  ["organizations", "organizations"],
  ["trust", "trust changes"],
];

// Which event kinds each pulse group shows.
export const PULSE_KINDS: Record<PulseGroup, string[]> = {
  trades: ["trade"],
  gifts: ["gift"],
  starving: ["starving"],
  population: ["arrived", "left"],
  organizations: ["joined_org", "left_org", "founded_org"],
  trust: ["trusted", "distrusted"],
};

/** The edge id serialize.py gives the edge between two nodes on a layer. */
export function edgeId(a: string, b: string, layer: Layer): string {
  return a < b ? `${a}|${b}|${layer}` : `${b}|${a}|${layer}`;
}

// --- Community outlines ----------------------------------------------------------------------

type Point = [number, number];

/** A padded outline around a group of nodes (circles), as an SVG path in model coordinates. */
export function hullPath(circles: { x: number; y: number; r: number }[]): string {
  const points: Point[] = [];
  for (const { x, y, r } of circles) {
    for (let i = 0; i < 12; i++) {
      const angle = (i / 12) * 2 * Math.PI;
      points.push([x + r * Math.cos(angle), y + r * Math.sin(angle)]);
    }
  }
  const hull = convexHull(points);
  return hull.length ? `M${hull.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join("L")}Z` : "";
}

/** Andrew's monotone chain: the convex hull of a set of points, counter-clockwise. */
function convexHull(points: Point[]): Point[] {
  const sorted = [...points].sort((p, q) => p[0] - q[0] || p[1] - q[1]);
  if (sorted.length < 3) return sorted;
  const cross = (o: Point, a: Point, b: Point) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  const half = (list: Point[]) => {
    const chain: Point[] = [];
    for (const p of list) {
      while (chain.length >= 2 && cross(chain[chain.length - 2], chain[chain.length - 1], p) <= 0) chain.pop();
      chain.push(p);
    }
    chain.pop();
    return chain;
  };
  return [...half(sorted), ...half([...sorted].reverse())];
}
