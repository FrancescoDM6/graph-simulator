import { useEffect, useState } from "react";

/** The playback cursor: which tick is shown, and whether it is advancing by itself.
 * `lastTick` may grow while a run is still being computed; playback keeps up with it. */
export function usePlayback(lastTick: number) {
  const [tick, setTickRaw] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(8); // ticks per second

  useEffect(() => {
    if (!playing) return;
    const timer = window.setInterval(
      () => setTickRaw((t) => (t < lastTick ? t + 1 : t)),
      1000 / speed,
    );
    return () => window.clearInterval(timer);
  }, [playing, speed, lastTick]);

  const setTick = (t: number) => setTickRaw(Math.max(0, Math.min(lastTick, Math.round(t))));
  return { tick, setTick, playing, setPlaying, speed, setSpeed };
}
