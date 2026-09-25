import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "./api";
import { CausalTrail } from "./CausalTrail";
import { Communities } from "./Communities";
import { EventFeed } from "./EventFeed";
import { Experiments } from "./Experiments";
import { runLabel } from "./format";
import { GraphView } from "./GraphView";
import { droughtPeriods, useRunData } from "./hooks/useRunData";
import { usePlayback } from "./hooks/usePlayback";
import { useSnapshot } from "./hooks/useSnapshot";
import { Inspector } from "./Inspector";
import { Legend } from "./Legend";
import { MetricsBar } from "./MetricsBar";
import { NewRunDialog, type NewRunRequest } from "./NewRunDialog";
import { Playback } from "./Playback";
import { RunBar, type Tab } from "./RunBar";
import { Timeline } from "./Timeline";
import { LAYERS, type Layer, type RunInfo, type Scenario } from "./types";

const RUN_LIST_REFRESH_MS = 3000; // while any run is still computing

export function App() {
  const [scenario, setScenario] = useState<Scenario | null>(null);
  const [runs, setRuns] = useState<RunInfo[]>([]);
  const [runA, setRunA] = useState<number | null>(null);
  const [runB, setRunB] = useState<number | null>(null);
  const [tab, setTab] = useState<Tab>("explore");
  const [bottomTab, setBottomTab] = useState<"events" | "communities">("events");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [community, setCommunity] = useState<number | null>(null);
  const [whyEvent, setWhyEvent] = useState<number | null>(null);
  const [visibleLayers, setVisibleLayers] = useState<Set<Layer>>(new Set(LAYERS));
  const [newRunOpen, setNewRunOpen] = useState(false);
  const [error, setError] = useState("");

  // --- the scenario and the list of runs ---

  useEffect(() => {
    api.scenario().then(setScenario, (e) => setError(`Can't reach the server on port 8000 (${e})`));
  }, []);

  const refreshRuns = useCallback(async () => {
    const all = await api.runs();
    const playable = all.filter((run) => run.level === "full" && run.status !== "failed");
    setRuns(playable);
    return playable;
  }, []);

  useEffect(() => {
    refreshRuns().then((playable) => {
      if (playable.length) setRunA((current) => current ?? playable[playable.length - 1].id);
    });
  }, [refreshRuns]);

  const anyRunning = runs.some((run) => run.status === "running");
  useEffect(() => {
    if (!anyRunning) return;
    const timer = window.setInterval(refreshRuns, RUN_LIST_REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [anyRunning, refreshRuns]);

  // --- the runs being shown ---

  const timelineMetrics = useMemo(
    () => [...(scenario?.timeline.map((t) => t.metric) ?? []), "drought"],
    [scenario],
  );
  const a = useRunData(runA, timelineMetrics);
  const b = useRunData(runB, timelineMetrics);
  const lastTick = a.run?.ticks_done ?? 0;
  const lastTickB = b.run?.ticks_done ?? 0;
  const playback = usePlayback(lastTick);
  const snapshotA = useSnapshot(runA, playback.tick, lastTick);
  const snapshotB = useSnapshot(runB, Math.min(playback.tick, lastTickB), lastTickB);
  const droughts = droughtPeriods(a.series.drought);

  const colors = useMemo(
    () => Object.fromEntries(Object.entries(scenario?.occupations ?? {}).map(([name, o]) => [name, o.color])),
    [scenario],
  );
  const stapleGood = Object.entries(scenario?.goods ?? {}).find(([, g]) => g.eaten_per_tick > 0)?.[0] ?? "";
  const highlight = useMemo(() => {
    if (community === null || !snapshotA) return null;
    return new Set(snapshotA.nodes.filter((n) => n.kind === "agent" && n.community === community).map((n) => n.id));
  }, [community, snapshotA]);

  // --- actions ---

  function jump(tick: number, subject: string | null = null) {
    playback.setPlaying(false);
    playback.setTick(tick);
    if (subject) setSelectedId(subject);
  }

  function selectRunA(id: number | null) {
    setRunA(id);
    setSelectedId(null);
    setCommunity(null);
    setWhyEvent(null);
  }

  async function startRun(request: NewRunRequest, compareWithCurrent: boolean) {
    setNewRunOpen(false);
    try {
      const run = await api.startRun(request);
      await refreshRuns();
      if (compareWithCurrent && runA !== null) setRunB(run.id);
      else selectRunA(run.id);
    } catch (e) {
      setError(String(e));
    }
  }

  async function openRun(runId: number) {
    try {
      const full = await api.materialize(runId);
      await refreshRuns();
      selectRunA(full.id);
      setRunB(null);
      setTab("explore");
    } catch (e) {
      setError(String(e));
    }
  }

  function toggleLayer(layer: Layer) {
    setVisibleLayers((old) => {
      const next = new Set(old);
      if (next.has(layer)) next.delete(layer);
      else next.add(layer);
      return next;
    });
  }

  // --- layout ---

  if (!scenario) return <div className="loading">{error || "Loading the scenario…"}</div>;

  const runInfoA = runs.find((r) => r.id === runA);
  const runInfoB = runs.find((r) => r.id === runB);
  const liveIds = new Set(snapshotA?.nodes.map((n) => n.id) ?? []);

  return (
    <div className={`app ${tab}`}>
      <RunBar
        runs={runs}
        runA={runA}
        runB={runB}
        onSelectA={selectRunA}
        onSelectB={setRunB}
        onNewRun={() => setNewRunOpen(true)}
        tab={tab}
        onTab={setTab}
      />
      {error && (
        <div className="error-bar" onClick={() => setError("")}>
          {error} (click to dismiss)
        </div>
      )}

      {tab === "experiments" && <Experiments scenario={scenario} onOpenRun={openRun} />}

      {tab === "explore" && runA === null && (
        <div className="empty">
          No runs yet. Press <b>New run…</b> to compute one, or open a run from the Experiments tab.
        </div>
      )}

      {tab === "explore" && runA !== null && (
        <>
          <Playback
            tick={playback.tick}
            lastTick={lastTick}
            totalTicks={a.run?.ticks ?? 0}
            playing={playback.playing}
            speed={playback.speed}
            drought={snapshotA?.drought ?? false}
            onTick={playback.setTick}
            onPlaying={playback.setPlaying}
            onSpeed={playback.setSpeed}
            visibleLayers={visibleLayers}
            onToggleLayer={toggleLayer}
          />
          {snapshotA ? <MetricsBar snapshot={snapshotA} onSelect={setSelectedId} /> : <div className="metrics-bar" />}
          <main className="main">
            <div className={`graphs ${runB !== null ? "compare" : ""}`}>
              <div className="graph-panel">
                {snapshotA && (
                  <GraphView
                    key={runA}
                    snapshot={snapshotA}
                    colors={colors}
                    visibleLayers={visibleLayers}
                    selectedId={selectedId}
                    highlight={highlight}
                    onSelect={setSelectedId}
                  />
                )}
                {runInfoA && runB !== null && <div className="graph-title">{runLabel(runInfoA)}</div>}
                <Legend colors={colors} />
              </div>
              {runB !== null && (
                <div className="graph-panel">
                  {snapshotB && (
                    <GraphView
                      key={runB}
                      snapshot={snapshotB}
                      colors={colors}
                      visibleLayers={visibleLayers}
                      selectedId={selectedId}
                      highlight={null}
                      onSelect={setSelectedId}
                    />
                  )}
                  {runInfoB && (
                    <div className="graph-title">
                      {runLabel(runInfoB)}
                      {playback.tick > lastTickB && " (not computed this far yet)"}
                    </div>
                  )}
                </div>
              )}
            </div>
            {snapshotA && (
              <Inspector
                runId={runA}
                snapshot={snapshotA}
                selectedId={selectedId}
                lastTick={lastTick}
                droughts={droughts}
                stapleGood={stapleGood}
                onSelect={setSelectedId}
                onJump={(tick) => jump(tick)}
                onWhy={setWhyEvent}
              />
            )}
          </main>
          <div className="bottom">
            <Timeline
              charts={scenario.timeline}
              seriesA={a.series}
              seriesB={runB !== null ? b.series : null}
              lastTick={Math.max(lastTick, 1)}
              cursor={playback.tick}
              onPick={(tick) => jump(tick)}
            />
            <div className="bottom-right">
              <nav className="tabs small-tabs">
                <button className={bottomTab === "events" ? "active" : ""} onClick={() => setBottomTab("events")}>
                  Events
                </button>
                <button
                  className={bottomTab === "communities" ? "active" : ""}
                  onClick={() => setBottomTab("communities")}
                >
                  Communities
                </button>
              </nav>
              {bottomTab === "events" ? (
                <EventFeed
                  runId={runA}
                  cursor={playback.tick}
                  liveIds={liveIds}
                  onSelect={setSelectedId}
                  onJump={(tick) => jump(tick)}
                  onWhy={setWhyEvent}
                />
              ) : (
                <Communities
                  runId={runA}
                  lastTick={Math.max(lastTick, 1)}
                  cursor={playback.tick}
                  selected={community}
                  onSelect={(id, tick) => {
                    setCommunity(id === community ? null : id);
                    setSelectedId(null);
                    jump(tick);
                  }}
                />
              )}
            </div>
          </div>
          {whyEvent !== null && (
            <CausalTrail runId={runA} eventId={whyEvent} onClose={() => setWhyEvent(null)} onJump={jump} />
          )}
        </>
      )}

      {newRunOpen && (
        <NewRunDialog
          scenario={scenario}
          seed={runInfoA?.seed ?? scenario.seed}
          ticks={runInfoA?.ticks ?? scenario.ticks}
          onCancel={() => setNewRunOpen(false)}
          onStart={startRun}
        />
      )}
    </div>
  );
}
