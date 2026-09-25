// Every visual encoding lives in this file: how simulation state becomes size, colour and shape.
import type cytoscape from "cytoscape";
import type { GraphEdge, GraphNode, Layer, Occupation } from "./types";

// Tableau 10: distinguishable categorical colours for communities.
export const COMMUNITY_COLORS = [
  "#4e79a7", "#e15759", "#76b7b2", "#59a14f", "#edc948",
  "#b07aa1", "#ff9da7", "#9c755f", "#f28e2b", "#bab0ac",
];
const NO_COMMUNITY_COLOR = "#5b606b";

export const OCCUPATION_COLORS: Record<Occupation, string> = {
  farmer: "#7bd88f",
  miner: "#c9a27e",
  merchant: "#f5d76e",
};
const STARVING_COLOR = "#ff4d4d";

export const LAYER_COLORS: Record<Layer, string> = {
  social: "#6ea8fe",
  trade: "#f0a04b",
  membership: "#b58df2",
  access: "#6b7280",
};

const RECENT_TRADE_TICKS = 20; // trade edges fade out over this many ticks without a trade

export function communityColor(community: number): string {
  return community < 0 ? NO_COMMUNITY_COLOR : COMMUNITY_COLORS[community % COMMUNITY_COLORS.length];
}

/** Data fields the stylesheet below reads, computed from a node's simulation state. */
export function nodeData(node: GraphNode): Record<string, string | number> {
  switch (node.kind) {
    case "agent":
      return {
        id: node.id,
        kind: node.kind,
        label: node.name,
        size: Math.min(60, 14 + 4 * Math.sqrt(Math.max(node.coin, 0))), // size = wealth
        fill: communityColor(node.community),
        border:
          node.hunger_ticks > 0 ? STARVING_COLOR : (OCCUPATION_COLORS[node.occupation] ?? "#999999"),
      };
    case "town":
      return { id: node.id, kind: node.kind, label: node.name, size: 46, fill: "#343944", border: "#8a90a0" };
    case "site":
      return {
        id: node.id,
        kind: node.kind,
        label: node.name,
        size: 26,
        fill: node.site_kind === "farm" ? "#3f6b46" : "#55555f",
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
      "transition-property": "width, height, background-color, border-color",
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
  { selector: ".faded", style: { opacity: 0.12 } },
  {
    selector: "node:selected",
    style: { "border-width": 5, "border-color": "#ffffff", "overlay-opacity": 0 },
  },
];

/** Rows for the on-screen legend. */
export const LEGEND = {
  occupations: Object.entries(OCCUPATION_COLORS) as [Occupation, string][],
  layers: Object.entries(LAYER_COLORS) as [Layer, string][],
  starving: STARVING_COLOR,
};
