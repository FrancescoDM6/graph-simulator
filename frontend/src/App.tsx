import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api";
import { CausalTrail } from "./CausalTrail";
import { CHART_BACKGROUND } from "./charts/LineChart";
import { Communities } from "./Communities";
import { EventFeed } from "./EventFeed";
import { Experiments } from "./Experiments";
import { ExportMenu } from "./ExportMenu";
import { composeFigure, type Figure, fileStem, runDescription } from "./export";
import { runLabel } from "./format";
import { GraphControls } from "./GraphControls";
import { COLOR_MODES, type ColorMode, PULSE_GROUPS, PULSE_KINDS, type PulseGroup } from "./graphStyle";
import { GroupPage } from "./GroupPage";
import { type GraphExport, GraphView } from "./GraphView";
import { droughtPeriods, useRunData } from "./hooks/useRunData";
import { usePlayback } from "./hooks/usePlayback";
import { useSnapshot } from "./hooks/useSnapshot";
import { useTickEvents } from "./hooks/useTickEvents";
import { type Group, Inspector } from "./Inspector";
import { Legend } from "./Legend";
import { MetricsBar } from "./MetricsBar";
import { NewRunDialog, type NewRunRequest } from "./NewRunDialog";
import { Playback } from "./Playback";
import { RunBar, type Tab } from "./RunBar";
import { Timeline } from "./Timeline";
import { LAYERS, type Layer, type RunInfo, type Scenario } from "./types";

const RUN_LIST_REFRESH_MS = 3000; // while any run is still computing
const TOWN_COLORS = ["#e15759", "#4e79a7", "#59a14f", "#f28e2b", "#b07aa1", "#76b7b2", "#edc948", "#ff9da7"];

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
  // Graph display options
  const [colorMode, setColorMode] = useState<ColorMode>("community");
  const [pulseGroups, setPulseGroups] = useState<Set<PulseGroup>>(new Set(PULSE_GROUPS.map(([g]) => g)));
  const [showHulls, setShowHulls] = useState(false);
  const [ego, setEgo] = useState<{ id: string; hops: number } | null>(null);
  const [group, setGroup] = useState<Group | null>(null); // community or organization page
  const [agentNames, setAgentNames] = useState<Map<string, string>>(new Map());
  const graphA = useRef<GraphExport>(null);
  const graphB = useRef<GraphExport>(null);

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
  const townIds = snapshotA?.nodes.filter((n) => n.kind === "town").map((n) => n.id).join(",") ?? "";
  const coloring = useMemo(
    () => ({
      mode: colorMode,
      occupationColors: colors,
      townColors: Object.fromEntries(townIds.split(",").filter(Boolean).map((id, i) => [id, TOWN_COLORS[i % TOWN_COLORS.length]])),
    }),
    [colorMode, colors, townIds],
  );
  const pulseKinds = [...pulseGroups].flatMap((g) => PULSE_KINDS[g]);
  const pulsesA = useTickEvents(runA, playback.tick, pulseKinds);
  const pulsesB = useTickEvents(runB, Math.min(playback.tick, lastTickB), pulseKinds);

  // Names of every agent that ever lived in run A (for people who have since left).
  useEffect(() => {
    setAgentNames(new Map());
    if (runA === null) return;
    api.agents(runA).then((agents) => setAgentNames(new Map(agents.map((a) => [a.agent_id, a.name]))));
  }, [runA, lastTick > 0]);
  const name = (id: string) => snapshotA?.nodes.find((n) => n.id === id)?.name ?? agentNames.get(id) ?? id;
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
    setEgo(null);
    setGroup(null);
  }

  function togglePulse(pulse: PulseGroup) {
    setPulseGroups((old) => {
      const next = new Set(old);
      if (next.has(pulse)) next.delete(pulse);
      else next.add(pulse);
      return next;
    });
  }

  /** The graph (both graphs in compare mode) as one figure, with a caption saying exactly what
   * it shows. */
  function graphFigure(runA: RunInfo | undefined, runB: RunInfo | undefined): Figure | null {
    const panels: (Figure & { title?: string })[] = [];
    const a = graphA.current?.svg({ background: CHART_BACKGROUND });
    if (a) panels.push({ ...a, title: runB && runA ? runLabel(runA) : undefined });
    const b = runB ? graphB.current?.svg({ background: CHART_BACKGROUND }) : undefined;
    if (b && runB) panels.push({ ...b, title: runLabel(runB) });
    if (panels.length === 0) return null;
    const modeLabel = COLOR_MODES.find(([m]) => m === colorMode)?.[1] ?? colorMode;
    const caption = [
      `tick ${playback.tick}; agents coloured by ${modeLabel}, border = occupation (red = starving), size = coin; ` +
        `layers shown: ${[...visibleLayers].join(", ")}${showHulls ? "; outlines = communities" : ""}` +
        `${ego ? `; ego view of ${name(ego.id)} (${ego.hops} hops)` : ""}`,
      runDescription(runA),
      ...(runB ? [runDescription(runB)] : []),
    ].join("\n");
    return composeFigure(panels, caption, { direction: "across", background: CHART_BACKGROUND, textColor: "#d7dae0" });
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
                    ref={graphA}
                    snapshot={snapshotA}
                    coloring={coloring}
                    visibleLayers={visibleLayers}
                    selectedId={selectedId}
                    highlight={highlight}
                    pulses={pulsesA}
                    ego={ego}
                    showHulls={showHulls}
                    onSelect={setSelectedId}
                  />
                )}
                {runInfoA && runB !== null && <div className="graph-title">{runLabel(runInfoA)}</div>}
                <GraphControls
                  colorMode={colorMode}
                  onColorMode={setColorMode}
                  pulses={pulseGroups}
                  onTogglePulse={togglePulse}
                  showHulls={showHulls}
                  onShowHulls={setShowHulls}
                  exportMenu={
                    <ExportMenu
                      stem={fileStem(runInfoA, `t${playback.tick}`, runInfoB ? `vs-run${runInfoB.id}` : "", "graph")}
                      title={`Graph at tick ${playback.tick}`}
                      description={runDescription(runInfoA) + (runInfoB ? `; right: ${runDescription(runInfoB)}` : "")}
                      figure={() => graphFigure(runInfoA, runB !== null ? runInfoB : undefined)}
                    />
                  }
                />
                {snapshotA && (
                  <Legend
                    mode={colorMode}
                    occupationColors={colors}
                    townColors={coloring.townColors}
                    snapshot={snapshotA}
                  />
                )}
              </div>
              {runB !== null && (
                <div className="graph-panel">
                  {snapshotB && (
                    <GraphView
                      key={runB}
                      ref={graphB}
                      snapshot={snapshotB}
                      coloring={coloring}
                      visibleLayers={visibleLayers}
                      selectedId={selectedId}
                      highlight={null}
                      pulses={pulsesB}
                      ego={ego}
                      showHulls={showHulls}
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
                run={runInfoA}
                name={name}
                ego={ego}
                onEgo={setEgo}
                onOpenGroup={setGroup}
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
              runA={runInfoA}
              runB={runB !== null ? runInfoB : undefined}
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
                  run={runInfoA}
                  lastTick={Math.max(lastTick, 1)}
                  cursor={playback.tick}
                  selected={community}
                  onSelect={(id, tick) => {
                    const deselect = id === community;
                    setCommunity(deselect ? null : id);
                    setGroup(deselect || id === null ? null : { kind: "community", id });
                    setSelectedId(null);
                    jump(tick);
                  }}
                />
              )}
            </div>
          </div>
          {group && (
            <GroupPage
              runId={runA}
              run={runInfoA}
              group={group}
              lastTick={Math.max(lastTick, 1)}
              cursor={playback.tick}
              droughts={droughts}
              name={name}
              onClose={() => setGroup(null)}
              onJump={(tick) => jump(tick)}
              onSelect={setSelectedId}
              onWhy={setWhyEvent}
            />
          )}
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
