import { useEffect, useReducer, useRef } from "react";
import { api } from "../api";
import type { Snapshot } from "../types";

const CHUNK = 40; // snapshots fetched per request
const KEEP_WITHIN = 400; // ticks either side of the cursor kept in memory

/** The stored snapshot of `runId` at `tick`. Snapshots are fetched in chunks around the cursor
 * (and the chunk after it, so playback doesn't stall). While a chunk loads, the nearest earlier
 * snapshot already in memory is returned instead. */
export function useSnapshot(runId: number | null, tick: number, lastTick: number): Snapshot | null {
  const cache = useRef(new Map<number, Snapshot>());
  const complete = useRef(new Set<number>()); // chunk starts fully loaded (or loading)
  const lastShown = useRef<{ runId: number; snapshot: Snapshot } | null>(null);
  const [, rerender] = useReducer((n: number) => n + 1, 0);

  useEffect(() => {
    cache.current = new Map();
    complete.current = new Set();
  }, [runId]);

  useEffect(() => {
    if (runId === null) return;
    const chunkStart = Math.floor(tick / CHUNK) * CHUNK;
    for (const start of [chunkStart, chunkStart + CHUNK]) {
      if (start > lastTick || complete.current.has(start)) continue;
      complete.current.add(start);
      const requestedFor = runId;
      api
        .snapshots(runId, start, CHUNK)
        .then((snapshots) => {
          if (requestedFor !== runId) return;
          for (const snapshot of snapshots) cache.current.set(snapshot.tick, snapshot);
          // A chunk of a run that is still computing may be partial: fetch it again later.
          if (snapshots.length < CHUNK) complete.current.delete(start);
          for (const t of cache.current.keys()) {
            if (Math.abs(t - tick) > KEEP_WITHIN) cache.current.delete(t);
          }
          for (const s of complete.current) {
            if (Math.abs(s - tick) > KEEP_WITHIN) complete.current.delete(s);
          }
          rerender();
        })
        .catch(() => complete.current.delete(start));
    }
  }, [runId, tick, lastTick]);

  if (runId === null) return null;
  for (let t = tick; t >= Math.max(0, tick - CHUNK * 2); t--) {
    const snapshot = cache.current.get(t);
    if (snapshot) {
      lastShown.current = { runId, snapshot };
      return snapshot;
    }
  }
  // Jumped somewhere not loaded yet: keep showing what was on screen (so the graph keeps its
  // layout) until the new chunk arrives.
  return lastShown.current?.runId === runId ? lastShown.current.snapshot : null;
}
