import { useCallback, useEffect, useRef, useState } from "react";
import type { Command, SimEvent, Snapshot } from "./types";

const RECONNECT_DELAY_MS = 1000;
const EVENT_FEED_LENGTH = 300; // how many recent events the feed keeps

export interface SimulationConnection {
  snapshot: Snapshot | null;
  connected: boolean;
  recentEvents: SimEvent[]; // newest first
  send: (command: Command) => void;
}

/** Keeps a WebSocket open to the server and exposes the latest snapshot. */
export function useSimulation(): SimulationConnection {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [connected, setConnected] = useState(false);
  const [recentEvents, setRecentEvents] = useState<SimEvent[]>([]);
  const socketRef = useRef<WebSocket | null>(null);
  const lastTickRef = useRef<number | null>(null);

  useEffect(() => {
    let stopped = false;
    let retryTimer: number | undefined;

    function connect() {
      const protocol = window.location.protocol === "https:" ? "wss" : "ws";
      const socket = new WebSocket(`${protocol}://${window.location.host}/ws`);
      socketRef.current = socket;
      socket.onopen = () => setConnected(true);
      socket.onclose = () => {
        setConnected(false);
        if (!stopped) retryTimer = window.setTimeout(connect, RECONNECT_DELAY_MS);
      };
      socket.onmessage = (message) => {
        const next: Snapshot = JSON.parse(message.data);
        // Snapshots are also re-sent after pause/speed changes; only a new tick brings new events.
        const isNewTick = next.tick !== lastTickRef.current;
        const isReset = lastTickRef.current !== null && next.tick < lastTickRef.current;
        lastTickRef.current = next.tick;
        if (isReset) setRecentEvents([]);
        if (isNewTick && next.events.length > 0) {
          const newestFirst = [...next.events].reverse();
          setRecentEvents((old) => [...newestFirst, ...old].slice(0, EVENT_FEED_LENGTH));
        }
        setSnapshot(next);
      };
    }

    connect();
    return () => {
      stopped = true;
      window.clearTimeout(retryTimer);
      socketRef.current?.close();
    };
  }, []);

  const send = useCallback((command: Command) => {
    const socket = socketRef.current;
    if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify(command));
  }, []);

  return { snapshot, connected, recentEvents, send };
}

/** Every event the server has logged for one node (agent, town, site or org). */
export async function fetchHistory(entityId: string): Promise<SimEvent[]> {
  const response = await fetch(`/api/entities/${encodeURIComponent(entityId)}/history`);
  if (!response.ok) throw new Error(`history request failed: ${response.status}`);
  return response.json();
}
