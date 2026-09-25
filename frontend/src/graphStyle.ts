// Every visual encoding lives in this file: how simulation state becomes size, colour and shape.
// Occupation colours come from scenario.toml ([occupations.<name>] color).
import type cytoscape from "cytoscape";
import type { AgentNode, GraphEdge, GraphNode, Layer } from "./types";

// Tableau 10: distinguishable categorical colours for communities.
export const COMMUNITY_COLORS = [
  "#4e79a7", "#e15759", "#76b7b2", "#59a14f", "#edc948",
  "#b07aa1", "#ff9da7", "#9c755f", "#f28e2b", "#bab0ac",
];
const NO_COMMUNITY_COLOR = "#5b606b";
const UNKNOWN_OCCUPATION_COLOR = "#999999";
export const STARVING_COLOR = "#ff4d4d";

export const LAYER_COLORS: Record<Layer, string> = {
  social: "#6ea8fe",
  trade: "#f0a04b",
  membership: "#b58df2",
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
        size: Math.min(60, 14 + 4 * Math.sqrt(Math.max(node.coin, 0))), // size = wealth
        fill: agentFill(node, coloring),
        border:
          node.hunger_ticks > 0
            ? STARVING_COLOR
            : (coloring.occupationColors[node.occupation] ?? UNKNOWN_OCCUPATION_COLOR),
        community: node.community,
      };
    case "town":
      return { id: node.id, kind: node.kind, label: node.name, size: 46, fill: "#343944", border: "#8a90a0" };
    case "site":
      return {
        id: node.id,
        kind: node.kind,
        label: node.name,
        size: 26,
        fill: "#48505e",
        border: node.stock < node.capacity * 0.1 ? STARVING_COLOR : "#8a90a0", // red = depleted
      };
    case "org":
      return {
        id: node.id,
        kind: node.kind,
        label: node.name,
        size: 16 + 3 * node.members,
        fill: "#5a3f8a",
        border: LAYER_COLORS.membership,
      };
  }
}

export function edgeData(edge: GraphEdge, tick: number): Record<string, string | number> {
  let width = 1;
  let opacity = 0.35;
  if (edge.layer === "social") {
    width = 1 + 4 * edge.strength;
    opacity = 0.15 + 0.6 * edge.strength;
  } else if (edge.layer === "trade") {
    const recency = Math.max(0, 1 - (tick - edge.last_active) / RECENT_TRADE_TICKS);
    width = 1 + 5 * edge.strength;
    opacity = 0.15 + 0.75 * recency;
  } else if (edge.layer === "membership") {
    opacity = 0.5;
  } else {
    opacity = 0.25;
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

export const stylesheet: cytoscape.StylesheetJson = [
  {
    selector: "node",
    style: {
      width: "data(size)",
      height: "data(size)",
      "background-color": "data(fill)",
      "border-color": "data(border)",
      "border-width": 3,
      label: "data(label)",
      color: "#d7dae0",
      "font-size": 9,
      "text-valign": "bottom",
      "text-margin-y": 3,
      "text-outline-color": "#14161a",
      "text-outline-width": 2,
      // Only sizes animate: colours change instantly, so an exported figure never catches a
      // colour half-way through a transition.
      "transition-property": "width, height",
      "transition-duration": 300,
    },
  },
  { selector: 'node[kind = "town"]', style: { shape: "round-rectangle", "font-size": 12, "font-weight": "bold" } },
  { selector: 'node[kind = "site"]', style: { shape: "diamond", "border-width": 2 } },
  { selector: 'node[kind = "org"]', style: { shape: "hexagon", "font-style": "italic" } },
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
  { selector: 'edge[layer = "access"]', style: { "line-style": "dashed" } },
  { selector: ".hidden", style: { visibility: "hidden", events: "no" } },
  { selector: ".ego-hidden", style: { display: "none" } }, // outside the ego neighbourhood
  // Event pulses (see PULSE_KINDS): briefly added when something happens to an element.
  { selector: "node.pulse-trade", style: { "overlay-color": "#ffd166", "overlay-opacity": 0.35, "overlay-padding": 6 } },
  { selector: "edge.pulse-trade", style: { "line-color": "#ffd166", opacity: 1, width: 6 } },
  { selector: ".pulse-gift", style: { "overlay-color": "#7bd88f", "overlay-opacity": 0.5, "overlay-padding": 10 } },
  { selector: ".pulse-starving", style: { "overlay-color": STARVING_COLOR, "overlay-opacity": 0.5, "overlay-padding": 10 } },
  { selector: ".pulse-population", style: { "overlay-color": "#ffffff", "overlay-opacity": 0.35, "overlay-padding": 12 } },
  { selector: ".pulse-org", style: { "overlay-color": LAYER_COLORS.membership, "overlay-opacity": 0.5, "overlay-padding": 10 } },
  { selector: "edge.pulse-trust-up", style: { "line-color": "#7bd88f", opacity: 1, width: 6 } },
  { selector: "edge.pulse-trust-down", style: { "line-color": STARVING_COLOR, opacity: 1, width: 6 } },
  { selector: ".faded", style: { opacity: 0.12 } },
  {
    selector: "node:selected",
    style: { "border-width": 5, "border-color": "#ffffff", "overlay-opacity": 0 },
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
