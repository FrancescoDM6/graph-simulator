import type { RunInfo } from "./types";

/** "#12 · seed 4 · no_gifting (broker_commission=0.8) · computing 400/2000" */
export function runLabel(run: RunInfo): string {
  const overrides = Object.entries(run.overrides)
    .map(([key, value]) => `${key.split(".").pop()}=${value}`)
    .join(", ");
  let label = `#${run.id} · seed ${run.seed} · ${run.variant}${overrides ? ` (${overrides})` : ""}`;
  if (run.label && run.label !== run.variant) label += ` · ${run.label}`;
  if (run.status === "running") label += ` · computing ${run.ticks_done}/${run.ticks}`;
  if (run.status === "failed") label += " · failed";
  return label;
}

/** A number with fixed decimals, or a dash when there is no value. */
export function formatNumber(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "–";
  return value.toFixed(digits);
}
