import { useEffect, useState } from "react";
import { api } from "./api";
import { type Bar, BarChart } from "./charts/BarChart";
import { fileStem, runDescription } from "./export";
import type { LedgerSummary, RunInfo } from "./types";

const RECENT = 100; // ticks in the "recent" window
const TRADE_CATEGORIES = new Set(["sale", "purchase", "commission", "gift_given", "gift_received"]);

interface Props {
  runId: number;
  run: RunInfo | undefined;
  agentId: string;
  cursor: number;
  stapleGood: string;
  name: (id: string) => string;
  onJump: (tick: number) => void;
  onWhy: (eventId: number) => void;
}

/** Where the agent's coin and goods came from and went, from the resource ledger: exact sums
 * by source, the partners behind them, and the trades themselves. */
export function Attribution({ runId, run, agentId, cursor, stapleGood, name, onJump, onWhy }: Props) {
  const [window, setWindow] = useState<"life" | "recent">("life");
  const [ledger, setLedger] = useState<LedgerSummary | null>(null);
  const first = window === "recent" ? Math.max(0, cursor - RECENT) : 0;

  useEffect(() => {
    let stale = false;
    const timer = setTimeout(() => api.agentFlows(runId, agentId, first, cursor).then((l) => !stale && setLedger(l)), 200);
    return () => {
      stale = true;
      clearTimeout(timer);
    };
  }, [runId, agentId, first, cursor]);

  if (!ledger) return null;
  const itemized = ledger.flows.length > 0;
  const byCategory = itemized ? ledger.by_category : lifetimeByCategory(ledger);
  const bars = (asset: string): Bar[] =>
    Object.entries(byCategory[asset] ?? {})
      .map(([category, value]) => ({ label: category.replace(/_/g, " "), value }))
      .sort((a, b) => Math.abs(b.value) - Math.abs(a.value));
  const change = (asset: string) => Object.values(byCategory[asset] ?? {}).reduce((s, v) => s + v, 0);
  const partner = (counterparty: string) =>
    counterparty.includes(">") ? counterparty.split(">").map(name).join(" → ") : name(counterparty);
  const trades = ledger.flows.filter((f) => f.asset === "coin" && TRADE_CATEGORIES.has(f.category)).slice(-30).reverse();
  const range = window === "recent" ? `ticks ${first}–${cursor}` : `up to tick ${cursor}`;
  const description = `${name(agentId)} (${agentId}), ${itemized ? range : "whole life"}, ${runDescription(run)}`;

  return (
    <div className="attribution">
      <div className="section-header">
        <h3>Where did it come from?</h3>
        <select value={window} onChange={(e) => setWindow(e.target.value as "life" | "recent")}>
          <option value="life">whole life</option>
          <option value="recent">last {RECENT} ticks</option>
        </select>
      </div>
      {!itemized && <div className="faint small">Lifetime totals only (this run stored no itemized ledger).</div>}
      <BarChart
        title={`Coin ${change("coin") >= 0 ? "+" : ""}${change("coin").toFixed(1)}, by source`}
        bars={bars("coin")}
        exportAs={{ stem: fileStem(run, agentId, "coin-sources"), description }}
      />
      {stapleGood && (
        <BarChart
          title={`${stapleGood} ${change(stapleGood) >= 0 ? "+" : ""}${change(stapleGood).toFixed(1)}, by source`}
          bars={bars(stapleGood)}
          exportAs={{ stem: fileStem(run, agentId, `${stapleGood}-sources`), description }}
        />
      )}
      {ledger.counterparties.length > 0 && (
        <>
          <div className="label attribution-label">Biggest partners (coin)</div>
          <ul className="rows plain">
            {ledger.counterparties.slice(0, 6).map((c) => (
              <li key={`${c.counterparty}-${c.category}`}>
                <span>
                  {partner(c.counterparty)} <span className="faint">{c.category.replace(/_/g, " ")}</span>
                </span>
                <span className={`num ${c.coin >= 0 ? "up" : "down"}`}>
                  {c.coin >= 0 ? "+" : ""}
                  {c.coin.toFixed(1)}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
      {trades.length > 0 && (
        <>
          <div className="label attribution-label">Recent trades and gifts</div>
          <ul className="rows">
            {trades.map((f, i) => (
              <li key={i}>
                <button className="tick link" onClick={() => onJump(f.tick)}>
                  {f.tick}
                </button>
                <span>
                  {f.category.replace(/_/g, " ")} {partner(f.counterparty)}{" "}
                  <span className={`num ${f.amount >= 0 ? "up" : "down"}`}>
                    {f.amount >= 0 ? "+" : ""}
                    {f.amount.toFixed(2)}
                  </span>
                  {f.event_id >= 0 && (
                    <button className="link why" onClick={() => onWhy(f.event_id)}>
                      why?
                    </button>
                  )}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

function lifetimeByCategory(ledger: LedgerSummary): Record<string, Record<string, number>> {
  const result: Record<string, Record<string, number>> = {};
  for (const { asset, category, amount } of ledger.lifetime) {
    (result[asset] ??= {})[category] = amount;
  }
  return result;
}
