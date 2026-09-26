// Every call the viewer makes to the backend (backend/graphsim/server.py).
import type {
  AgentLifetime,
  AgentTick,
  CommunityPage,
  CommunityRow,
  LedgerSummary,
  OrgPage,
  ExperimentReport,
  RunInfo,
  Scenario,
  Series,
  WorldInfo,
  SimEvent,
  Snapshot,
  TrailNode,
  TrustEntry,
} from "./types";

async function get<T>(path: string, params: Record<string, string | number | boolean | undefined> = {}) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) query.set(key, String(value));
  }
  const response = await fetch(`/api${path}${query.size ? `?${query}` : ""}`);
  if (!response.ok) throw new Error(`${path}: ${response.status} ${await response.text()}`);
  return (await response.json()) as T;
}

async function post<T>(path: string, body?: unknown) {
  const response = await fetch(`/api${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(detail.detail ?? String(response.status));
  }
  return (await response.json()) as T;
}

export const api = {
  scenario: () => get<Scenario>("/scenario"),
  worlds: () => get<WorldInfo[]>("/scenarios"),
  runs: () => get<RunInfo[]>("/runs"),
  run: (id: number) => get<RunInfo>(`/runs/${id}`),
  startRun: (request: {
    seed: number;
    ticks: number;
    scenario: string;
    variant: string;
    overrides: Record<string, unknown>; // may include generator.<param>
    label: string;
  }) => post<RunInfo>("/runs", request),
  materialize: (id: number) => post<RunInfo>(`/runs/${id}/materialize`),
  metrics: (id: number, names: string[]) =>
    get<{ names: string[]; series: Record<string, Series> }>(`/runs/${id}/metrics`, { names: names.join(",") }),
  snapshots: (id: number, first: number, count: number) =>
    get<Snapshot[]>(`/runs/${id}/snapshots`, { first, count }),
  events: (
    id: number,
    options: { first?: number; last?: number; entity?: string; detail?: boolean; kinds?: string[]; limit?: number },
  ) =>
    get<SimEvent[]>(`/runs/${id}/events`, {
      first: options.first,
      last: options.last,
      entity: options.entity,
      detail: options.detail,
      kinds: options.kinds?.join(","),
      limit: options.limit,
    }),
  trail: (id: number, eventId: number, depth = 3) =>
    get<TrailNode>(`/runs/${id}/events/${eventId}/trail`, { depth }),
  agents: (id: number) => get<AgentLifetime[]>(`/runs/${id}/agents`),
  agentHistory: (id: number, agentId: string) =>
    get<{ lifetime: AgentLifetime | null; ticks: AgentTick[] }>(`/runs/${id}/agents/${encodeURIComponent(agentId)}/history`),
  trust: (id: number, agent: string, first: number, last: number) =>
    get<TrustEntry[]>(`/runs/${id}/trust`, { agent, first, last }),
  communities: (id: number) =>
    get<{ communities: CommunityRow[]; sizes: Record<string, [number, number][]> }>(`/runs/${id}/communities`),
  experiment: (name: string) => get<ExperimentReport>(`/experiments/${encodeURIComponent(name)}`),
  agentFlows: (id: number, agentId: string, first: number, last: number) =>
    get<LedgerSummary>(`/runs/${id}/agents/${encodeURIComponent(agentId)}/flows`, { first, last }),
  community: (id: number, communityId: number) => get<CommunityPage>(`/runs/${id}/communities/${communityId}`),
  org: (id: number, orgId: string) => get<OrgPage>(`/runs/${id}/orgs/${encodeURIComponent(orgId)}`),
};
