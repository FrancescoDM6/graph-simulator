// Shapes of the messages the server sends. These mirror backend/graphsim/serialize.py and
// backend/graphsim/stats.py (TickMetrics) — change both sides together.

export type Layer = "social" | "trade" | "membership" | "access";
export const LAYERS: Layer[] = ["social", "trade", "membership", "access"];

export type Occupation = "farmer" | "miner" | "merchant";

export interface AgentNode {
  id: string;
  kind: "agent";
  name: string;
  occupation: Occupation;
  home: string;
  food: number;
  ore: number;
  coin: number;
  hunger_ticks: number;
  need: string;
  org: string | null;
  arrived: number;
  community: number; // -1 = not in any community
  betweenness: number; // trade-layer betweenness centrality
  degree: number;
}

export interface TownNode {
  id: string;
  kind: "town";
  name: string;
  residents: number;
}

export interface SiteNode {
  id: string;
  kind: "site";
  name: string;
  site_kind: "farm" | "mine";
  stock: number;
  capacity: number;
}

export interface OrgNode {
  id: string;
  kind: "org";
  name: string;
  home: string;
  founded: number;
  members: number;
}

export type GraphNode = AgentNode | TownNode | SiteNode | OrgNode;

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  layer: Layer;
  strength: number;
  trust: number | null; // social layer only
  created: number;
  last_active: number;
}

export interface SimEvent {
  tick: number;
  kind: string;
  subjects: string[];
  message: string;
  cause: string;
}

export interface TickMetrics {
  tick: number;
  population: number;
  farmers: number;
  miners: number;
  merchants: number;
  total_food: number;
  total_coin: number;
  price_food: number;
  price_ore: number;
  gini_coin: number;
  social_density: number;
  social_components: number;
  social_clustering: number;
  communities: number;
  avg_trust: number;
  trades: number;
  failed_trades: number;
  gifts: number;
  starving: number;
  orgs: number;
  drought: boolean;
  top_broker: string;
  top_broker_betweenness: number;
  merchant_broker_share: number;
}

export interface Snapshot {
  tick: number;
  seed: number;
  drought: boolean;
  prices: { food: number; ore: number };
  nodes: GraphNode[];
  edges: GraphEdge[];
  metrics: TickMetrics | null;
  events: SimEvent[]; // events from this tick only
  running: boolean;
  ticks_per_second: number;
}

export type Command =
  | { command: "play" }
  | { command: "pause" }
  | { command: "step" }
  | { command: "set_speed"; ticks_per_second: number }
  | { command: "reset"; seed: number };
