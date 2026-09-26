import type { Intervention, RunInfo } from "./types";

/** "#12 · hub_and_spokes · seed 4 · no_gifting (broker_commission=0.8) · computing 400/2000" */
export function runLabel(run: RunInfo): string {
  const overrides = Object.entries(run.overrides)
    .map(([key, value]) => `${key.split(".").pop()}=${value}`)
    .join(", ");
  let label = `#${run.id} · ${run.scenario} · seed ${run.seed} · ${run.variant}${overrides ? ` (${overrides})` : ""}`;
  if (run.parent_run !== null && run.branch_tick !== null) {
    const own = run.interventions.filter((i) => i.tick === run.branch_tick);
    label = `#${run.id} ↳ #${run.parent_run} @${run.branch_tick} · ${own.map(describeIntervention).join(", ") || "no changes"}`;
  }
  if (run.label && run.label !== run.variant) label += ` · ${run.label}`;
  if (run.status === "running") label += ` · computing ${run.ticks_done}/${run.ticks}`;
  if (run.status === "failed") label += " · failed";
  return label;
}

/** An intervention in a few words, e.g. "remove top_broker", "give richest 50 coin". */
export function describeIntervention(i: Intervention): string {
  const pair = (between: unknown) => (Array.isArray(between) ? between.join(" – ") : "");
  switch (i.kind) {
    case "remove_agent":
      return `remove ${i.target}`;
    case "give":
      return `give ${i.target} ${i.amount} ${i.asset}`;
    case "subsidize":
      return `subsidize ${i.occupation}s ${i.coin}/tick for ${i.ticks}`;
    case "set":
      return `${i.setting} = ${i.value}`;
    case "start_drought":
      return `drought for ${i.length}`;
    case "end_drought":
      return "end the drought";
    case "add_road":
    case "remove_road":
      return `${i.kind === "add_road" ? "road" : "close road"} ${pair(i.between)}`;
    case "add_site":
      return `new ${i.site_kind} in ${i.town}`;
    case "remove_site":
      return `close ${i.target}`;
    case "link":
      return `${i.layer} tie ${pair(i.between)}`;
    case "sever":
      return `cut ${pair(i.between)}`;
    case "set_trust":
      return `trust ${pair(i.between)} = ${i.value}`;
    case "found_org":
      return `org of ${Array.isArray(i.members) ? i.members.length : "?"}`;
    case "reseed":
      return "reshuffle chance";
    default:
      return i.kind;
  }
}

/** A number with fixed decimals, or a dash when there is no value. */
export function formatNumber(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "–";
  return value.toFixed(digits);
}
