import { useEffect, useReducer, useRef } from "react";
import { api } from "../api";
import type { SimEvent } from "../types";

const CHUNK = 40; // ticks of events fetched per request

/** The events of certain kinds at exactly `tick` (for flashing them on the graph). Fetched in
 * chunks of ticks, like snapshots, so playback doesn't make a request per tick. */
export function useTickEvents(runId: number | null, tick: number, kinds: string[]): SimEvent[] {
  const byTick = useRef(new Map<number, SimEvent[]>());
  const loaded = useRef(new Set<number>()); // chunk starts loaded or loading
  const [, rerender] = useReducer((n: number) => n + 1, 0);
  const kindList = kinds.join(",");

  useEffect(() => {
    byTick.current = new Map();
    loaded.current = new Set();
  }, [runId, kindList]);

  useEffect(() => {
    if (runId === null || !kindList) return;
    const chunkStart = Math.floor(tick / CHUNK) * CHUNK;
    for (const start of [chunkStart, chunkStart + CHUNK]) {
      if (loaded.current.has(start)) continue;
      loaded.current.add(start);
      api
        .events(runId, { first: start, last: start + CHUNK - 1, detail: true, kinds: kindList.split(","), limit: 5000 })
        .then((events) => {
          for (const event of events) {
            const list = byTick.current.get(event.tick) ?? [];
            list.push(event);
            byTick.current.set(event.tick, list);
          }
          rerender();
        })
        .catch(() => loaded.current.delete(start));
    }
  }, [runId, tick, kindList]);

  return byTick.current.get(tick) ?? NO_EVENTS;
}

const NO_EVENTS: SimEvent[] = [];
