// Shapes of what the API returns. These mirror backend/graphsim/server.py, storage.py and
// serialize.py; change both sides together.

export type Layer = "social" | "trade" | "membership" | "access";
export const LAYERS: Layer[] = ["social", "trade", "membership", "access"];

// --- scenario.toml, as described by GET /api/scenario ----------------------------------------

export interface OccupationSpec {
  works_at: string;
  output: number;
  tool: string;
  brokers: boolean;
  reach: string;
  color: string;
}

export interface GoodSpec {
  eaten_per_tick: number;
  reserve: number;
}

export interface TimelineSeries {
  metric: string;
  label: string;
  color: string;
}

export interface PhenomenonSpec {
  description: string;
  measure: string;
  present_if: string;
}

export interface Scenario {
  name: string;
  default_scenario: string; // the world used unless another is chosen (scenarios/<name>.toml)
  seed: number;
  ticks: number;
  goods: Record<string, GoodSpec>;
  occupations: Record<string, OccupationSpec>;
  mechanisms: Record<string, boolean | string>;
  mechanism_choices: Record<string, string[]>;
  variants: Record<string, string>; // name -> description
  experiments: Record<
    string,
    { description: string; seeds: number; scenarios: string[]; variants: string[]; ticks: number }
  >;
  phenomena: Record<string, PhenomenonSpec>;
  timeline: TimelineSeries[];
}

/** A world from scenarios/: its map as built (generated ones included), totals and shape. */
export interface WorldInfo {
  name: string;
  title: string;
  description: string;
  generator: Record<string, string | number> | null; // null: a written-out map
  towns: {
    name: string;
    position: [number, number]; // 0..1 across and down
    sites: { name: string; kind: string; scale: number }[];
    founding: Record<string, number>;
  }[];
  roads: { from: string; to: string }[];
  summary: Record<string, number | string>; // people, people.<occupation>, towns, roads, diameter…
  variants: string[]; // the variants that can run in this world
}

// --- runs -------------------------------------------------------------------------------------

export interface RunInfo {
  id: number;
  created: string;
  scenario: string; // the world (scenarios/<name>.toml)
  variant: string;
  overrides: Record<string, unknown>;
  seed: number;
  ticks: number;
  level: "summary" | "full";
  experiment: string;
  label: string;
  status: "running" | "done" | "failed";
  ticks_done: number;
  code_version: string; // git commit the run was computed with
  config_hash: string; // identifies the exact settings
  parent_run: number | null; // a branch: the run it branched from
  branch_tick: number | null; // ... and the tick it starts at
  interventions: Intervention[]; // every intervention in its history
}

/** A change made to a world at a tick (backend/graphsim/interventions.py), e.g.
 * {tick: 1000, kind: "remove_agent", target: "top_broker"}. */
export type Intervention = { tick?: number; kind: string } & Record<string, unknown>;

/** A run's family: what it branched from, its siblings and its own branches. */
export interface Lineage {
  run: RunInfo & { final: Record<string, number> };
  ancestors: (RunInfo & { final: Record<string, number> })[];
  siblings: (RunInfo & { final: Record<string, number> })[];
  children: (RunInfo & { final: Record<string, number> })[];
  intervention_kinds: Record<string, string[]>; // kind -> its parameters
}

export type Series = [number, number][]; // [tick, value][]

export interface AgentNode {
  id: string;
  kind: "agent";
  name: string;
  occupation: string;
  home: string;
  inventory: Record<string, number>;
  coin: number;
  hunger_ticks: number;
  need: string;
  org: string | null;
  arrived: number;
  community: number; // -1 = none
  betweenness: number;
  degree: number;
  mean_trust: number | null; // over the agent's social ties
}

export interface TownNode {
  id: string;
  kind: "town";
  name: string;
  residents: number;
  position?: [number, number]; // on the world's map, 0..1 (missing in runs from before scenarios)
}

export interface SiteNode {
  id: string;
  kind: "site";
  name: string;
  site_kind: string;
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
  trust: number | null;
  created: number;
  last_active: number;
}

// Metric name -> value, e.g. "gini_coin", "population.farmer", "stock.food".
export type TickMetrics = Record<string, number>;

export interface Snapshot {
  tick: number;
  seed: number;
  drought: boolean;
  prices: Record<string, number>;
  nodes: GraphNode[];
  edges: GraphEdge[];
  metrics: TickMetrics | null;
  top_broker: string;
}

export interface SimEvent {
  id: number;
  tick: number;
  kind: string;
  subjects: string[];
  message: string;
  cause: string;
  detail: boolean;
  caused_by: number[];
}

// A causal trail: an event with its causes nested. `causes` is null when not expanded yet.
export interface TrailNode extends Partial<SimEvent> {
  id: number;
  missing?: boolean; // the cause wasn't stored (summary-level run)
  causes?: TrailNode[] | null;
}

export interface AgentTick {
  tick: number;
  occupation: string;
  org: string | null;
  community: number;
  coin: number;
  inventory: Record<string, number>;
  mean_trust: number | null;
  social_ties: number;
  trade_ties: number;
  betweenness: number;
  bought: number;
  sold: number;
  brokered: number;
  gifts_given: number;
  gifts_received: number;
  hunger: number;
}

export interface AgentLifetime {
  agent_id: string;
  name: string;
  occupation: string;
  home: string;
  arrived: number;
  departed: number | null;
  departure_event: number | null;
  founding: number;
}

export interface TrustEntry {
  tick: number;
  a: string;
  b: string;
  before: number;
  after: number;
  event_id: number;
  event: SimEvent | null;
}

export interface CommunityRow {
  community_id: number;
  born: number;
  died: number | null;
  fate: "alive" | "merged" | "split" | "dissolved";
  parent: number | null;
  merged_into: number | null;
  peak_size: number;
  members_ever: number;
  mean_turnover: number;
  continuations: number;
}

// --- experiments ------------------------------------------------------------------------------

export interface ExperimentRun {
  label: string;
  seed: number;
  run_id: number;
  measures: Record<string, number>;
  present: Record<string, boolean>;
}

export interface SummaryRow {
  label: string;
  measure: string; // a measure name, or "present:<phenomenon>"
  n: number;
  mean: number | null;
  median: number | null;
  p5: number | null; // for presence rows: the 95% interval's lower bound
  p95: number | null;
}

export interface PairedRow {
  label: string;
  measure: string;
  n: number;
  median_diff: number | null;
  mean_diff: number | null;
  same_sign: number | null;
}

export interface ExperimentReport {
  experiment: string;
  baseline: string | null;
  labels: string[];
  runs: ExperimentRun[];
  summary: SummaryRow[];
  paired: PairedRow[];
}

// --- the resource ledger and group pages -------------------------------------------------------

export interface FlowEntry {
  tick: number;
  asset: string; // "coin" or a good
  category: string; // sale, purchase, commission, gift_given, levy_paid, eaten, ...
  amount: number; // + gained, - lost
  counterparty: string; // another agent; for a commission "buyer>seller"
  event_id: number;
}

export interface LedgerSummary {
  flows: FlowEntry[];
  by_category: Record<string, Record<string, number>>; // asset -> category -> total
  counterparties: { counterparty: string; category: string; coin: number }[];
  lifetime: { asset: string; category: string; amount: number }[];
}

export interface GroupHistoryRow {
  tick: number;
  size: number;
  density: number | null;
  trust: number | null;
  trade?: number | null;
}

export interface MembershipChange {
  tick: number;
  joined: string[];
  left: string[];
}

export interface CommunityPage {
  record: CommunityRow;
  history: GroupHistoryRow[];
  changes: MembershipChange[];
  events: SimEvent[];
}

export interface OrgPage {
  name: string;
  history: GroupHistoryRow[];
  changes: MembershipChange[];
  events: SimEvent[];
}
