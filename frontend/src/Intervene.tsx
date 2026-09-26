import { useState } from "react";
import { describeIntervention } from "./format";
import type { Intervention, Scenario, Snapshot } from "./types";

// What each field of an intervention form picks.
type FieldType =
  "agent" | "town" | "site" | "number" | "text" | "value" | "asset" | "occupation" | "layer" | "site_kind";

interface Field {
  key: string; // the intervention's parameter; "between.0" fills a list
  label: string;
  type: FieldType;
  initial?: string;
  optional?: boolean; // left empty: not included
}

interface Form {
  group: string;
  kind: string;
  title: string;
  fields: Field[];
}

// Every kind of intervention (backend/graphsim/interventions.py) and how to fill it in.
const FORMS: Form[] = [
  {
    group: "Shocks",
    kind: "remove_agent",
    title: "Remove an agent",
    fields: [{ key: "target", label: "Who", type: "agent" }],
  },
  {
    group: "Shocks",
    kind: "start_drought",
    title: "Start a drought",
    fields: [{ key: "length", label: "Ticks", type: "number", initial: "60" }],
  },
  { group: "Shocks", kind: "end_drought", title: "End the drought", fields: [] },
  {
    group: "Economy",
    kind: "give",
    title: "Give (or take) coin or goods",
    fields: [
      { key: "target", label: "Who", type: "agent" },
      { key: "asset", label: "What", type: "asset", initial: "coin" },
      { key: "amount", label: "Amount (negative takes)", type: "number", initial: "20" },
    ],
  },
  {
    group: "Economy",
    kind: "subsidize",
    title: "Subsidize an occupation",
    fields: [
      { key: "occupation", label: "Occupation", type: "occupation" },
      { key: "coin", label: "Coin per tick", type: "number", initial: "1" },
      { key: "ticks", label: "For ticks", type: "number", initial: "100" },
    ],
  },
  {
    group: "Economy",
    kind: "set",
    title: "Change a setting",
    fields: [
      { key: "setting", label: "Setting (section.key)", type: "text", initial: "trade.broker_commission" },
      { key: "value", label: "New value", type: "value", initial: "0.8" },
    ],
  },
  {
    group: "Geography",
    kind: "add_road",
    title: "Build a road",
    fields: [
      { key: "between.0", label: "From", type: "town" },
      { key: "between.1", label: "To", type: "town" },
    ],
  },
  {
    group: "Geography",
    kind: "remove_road",
    title: "Close a road",
    fields: [
      { key: "between.0", label: "From", type: "town" },
      { key: "between.1", label: "To", type: "town" },
    ],
  },
  {
    group: "Geography",
    kind: "add_site",
    title: "Open a farm or mine",
    fields: [
      { key: "town", label: "Town", type: "town" },
      { key: "site_kind", label: "Kind", type: "site_kind" },
      { key: "scale", label: "Size (1 = standard)", type: "number", initial: "1" },
    ],
  },
  {
    group: "Geography",
    kind: "remove_site",
    title: "Close a farm or mine",
    fields: [{ key: "target", label: "Site", type: "site" }],
  },
  {
    group: "Social",
    kind: "link",
    title: "Create a tie",
    fields: [
      { key: "between.0", label: "Between", type: "agent" },
      { key: "between.1", label: "And", type: "agent" },
      { key: "layer", label: "Layer", type: "layer", initial: "social" },
      { key: "strength", label: "Strength", type: "number", initial: "0.8" },
      { key: "trust", label: "Trust", type: "number", initial: "0.8" },
    ],
  },
  {
    group: "Social",
    kind: "sever",
    title: "Cut a tie",
    fields: [
      { key: "between.0", label: "Between", type: "agent" },
      { key: "between.1", label: "And", type: "agent" },
      { key: "layer", label: "Layer", type: "layer", initial: "social" },
    ],
  },
  {
    group: "Social",
    kind: "set_trust",
    title: "Set trust",
    fields: [
      { key: "between.0", label: "Between", type: "agent" },
      { key: "between.1", label: "And", type: "agent" },
      { key: "value", label: "Trust (0–1)", type: "number", initial: "0.1" },
    ],
  },
  {
    group: "Social",
    kind: "found_org",
    title: "Found an organization",
    fields: [
      { key: "members.0", label: "Founder", type: "agent" },
      { key: "members.1", label: "Member", type: "agent", optional: true },
      { key: "members.2", label: "Member", type: "agent", optional: true },
    ],
  },
  { group: "Control", kind: "reseed", title: "Reshuffle chance (same world, new random stream)", fields: [] },
];

// Agents chosen by a rule at the branch tick (interventions.resolve).
const AGENT_RULES: [string, string][] = [
  ["top_broker", "the top broker"],
  ["richest", "the richest agent"],
  ["poorest", "the poorest agent"],
  ["most_connected", "the most connected agent"],
  ["starving", "everyone starving"],
];

interface Props {
  tick: number; // the branch tick: the interventions happen at its start
  snapshot: Snapshot; // the world at the cursor, for picking agents, towns and sites
  scenario: Scenario;
  selectedId: string | null; // pre-filled where it fits
  queue: Intervention[];
  onQueue: (queue: Intervention[]) => void;
  onBranch: (label: string) => void;
  branching: boolean;
  error: string;
}

/** Change the world at a tick: queue interventions, then branch. The run shown stays as it
 * is; the branch is a new run, identical up to the tick, that opens next to it. */
export function Intervene({ tick, snapshot, scenario, selectedId, queue, onQueue, onBranch, branching, error }: Props) {
  const [kind, setKind] = useState(FORMS[0].kind);
  const [values, setValues] = useState<Record<string, string>>({});
  const [label, setLabel] = useState("");
  const form = FORMS.find((f) => f.kind === kind)!;
  const agents = snapshot.nodes.filter((n) => n.kind === "agent").sort((a, b) => a.name.localeCompare(b.name));
  const towns = snapshot.nodes.filter((n) => n.kind === "town");
  const sites = snapshot.nodes.filter((n) => n.kind === "site");
  const selected = snapshot.nodes.find((n) => n.id === selectedId);

  const options = (type: FieldType): [string, string][] => {
    switch (type) {
      case "agent":
        return [
          ...AGENT_RULES.map(([v, l]): [string, string] => [v, `rule: ${l}`]),
          ...agents.map((a): [string, string] => [a.id, a.name]),
        ];
      case "town":
        return towns.map((t) => [t.id, t.name]);
      case "site":
        return sites.map((s) => [s.id, s.name]);
      case "asset":
        return [["coin", "coin"], ...Object.keys(scenario.goods).map((g): [string, string] => [g, g])];
      case "occupation":
        return Object.keys(scenario.occupations).map((o) => [o, o]);
      case "site_kind":
        return [
          ...new Set(
            Object.values(scenario.occupations)
              .map((o) => o.works_at)
              .filter(Boolean),
          ),
        ].map((k) => [k, k]);
      case "layer":
        return [
          ["social", "social"],
          ["trade", "trade"],
        ];
      default:
        return [];
    }
  };

  // A field's value: typed in, else its default, else the selected node if it fits, else the first option.
  const valueOf = (field: Field): string => {
    if (values[`${kind}.${field.key}`] !== undefined) return values[`${kind}.${field.key}`];
    if (field.initial !== undefined) return field.initial;
    if (field.optional) return "";
    if (selected && ((field.type === "agent" && selected.kind === "agent") || field.type === selected.kind)) {
      return selected.id;
    }
    return options(field.type)[field.key.endsWith(".1") ? 1 : 0]?.[0] ?? "";
  };

  function add() {
    const spec: Intervention = { kind };
    for (const field of form.fields) {
      const raw = valueOf(field);
      if (field.optional && !raw) continue;
      const value = field.type === "number" ? Number(raw) : field.type === "value" ? parseValue(raw) : raw;
      const [key, index] = field.key.split(".");
      if (index === undefined) spec[key] = value;
      else spec[key] = [...((spec[key] as unknown[]) ?? []), value];
    }
    onQueue([...queue, spec]);
  }

  const groups = [...new Set(FORMS.map((f) => f.group))];
  return (
    <div className="intervene">
      <div className="page-title">
        <div className="label">Intervene</div>
        <h2>Change the world at tick {tick}</h2>
        <p className="small">
          This run stays as it is. A new run, identical up to tick {tick}, starts from here with these changes and opens
          next to it, so you can compare the two histories.
        </p>
      </div>
      <section className="panel-section">
        <label className="field">
          <span>Change</span>
          <select value={kind} onChange={(e) => setKind(e.target.value)}>
            {groups.map((group) => (
              <optgroup key={group} label={group}>
                {FORMS.filter((f) => f.group === group).map((f) => (
                  <option key={f.kind} value={f.kind}>
                    {f.title}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
        </label>
        <div className="intervene-fields">
          {form.fields.map((field) => {
            const choices = options(field.type);
            const set = (v: string) => setValues({ ...values, [`${kind}.${field.key}`]: v });
            return (
              <label key={field.key} className="field">
                <span>{field.label}</span>
                {choices.length ? (
                  <select value={valueOf(field)} onChange={(e) => set(e.target.value)}>
                    {field.optional && <option value="">—</option>}
                    {choices.map(([v, l]) => (
                      <option key={v} value={v}>
                        {l}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input value={valueOf(field)} onChange={(e) => set(e.target.value)} />
                )}
              </label>
            );
          })}
        </div>
        <button className="small" onClick={add}>
          Add to this branch
        </button>
      </section>
      <section className="panel-section">
        <h3>This branch ({queue.length})</h3>
        {queue.length === 0 && (
          <div className="faint small">No changes yet: branching now copies this run from tick {tick}.</div>
        )}
        <ul className="rows plain">
          {queue.map((spec, i) => (
            <li key={i}>
              <span>{describeWithNames(spec, snapshot)}</span>
              <button className="ghost small" onClick={() => onQueue(queue.filter((_, j) => j !== i))} title="remove">
                ×
              </button>
            </li>
          ))}
        </ul>
        <label className="field">
          <span>Label</span>
          <input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="optional note" />
        </label>
        {error && <div className="error small">{error}</div>}
        <div className="intervene-actions">
          <button className="primary" disabled={branching} onClick={() => onBranch(label)}>
            {branching ? "Branching…" : `Branch from tick ${tick}`}
          </button>
        </div>
      </section>
    </div>
  );
}

/** "true"/"false" as booleans, numbers as numbers, anything else as text. */
function parseValue(raw: string): unknown {
  if (raw === "true" || raw === "false") return raw === "true";
  return raw.trim() !== "" && !Number.isNaN(Number(raw)) ? Number(raw) : raw;
}

/** The description, with node ids replaced by names. */
function describeWithNames(spec: Intervention, snapshot: Snapshot): string {
  const names = new Map(snapshot.nodes.map((n) => [n.id, n.name]));
  const named = Object.fromEntries(
    Object.entries(spec).map(([k, v]) => [
      k,
      Array.isArray(v) ? v.map((x) => names.get(String(x)) ?? x) : (names.get(String(v)) ?? v),
    ]),
  );
  return describeIntervention({ ...named, kind: spec.kind });
}
