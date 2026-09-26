import { useState } from "react";
import type { Scenario, WorldInfo } from "./types";

export interface NewRunRequest {
  seed: number;
  ticks: number;
  scenario: string; // the world (scenarios/<name>.toml)
  variant: string;
  overrides: Record<string, unknown>; // mechanism switches, generator.<param> values
  label: string;
}

interface Props {
  scenario: Scenario;
  worlds: WorldInfo[];
  world: string; // defaults: usually the run currently shown, so "same seed, one change" is easy
  seed: number;
  ticks: number;
  canCompare: boolean; // whether a run is open to compare with
  onCancel: () => void;
  onStart: (request: NewRunRequest, compareWithCurrent: boolean) => void;
}

const AS_VARIANT = ""; // mechanism left as the chosen variant (and scenario.toml) set it

/** Start a new stored run: a world, a seed, a variant from scenario.toml, the world's generator
 * parameters (for generated worlds) and optional switches. */
export function NewRunDialog({ scenario, worlds, world, seed, ticks, canCompare, onCancel, onStart }: Props) {
  const [worldName, setWorldName] = useState(world);
  const [params, setParams] = useState<Record<string, string>>(defaultParams(worlds, world));
  const [seedText, setSeedText] = useState(String(seed));
  const [ticksText, setTicksText] = useState(String(ticks));
  const [variant, setVariant] = useState("baseline");
  const [mechanisms, setMechanisms] = useState<Record<string, string>>({});
  const [label, setLabel] = useState("");
  const [compare, setCompare] = useState(canCompare);
  const chosen = worlds.find((w) => w.name === worldName);
  const variants = Object.entries(scenario.variants).filter(([name]) => chosen?.variants.includes(name) ?? true);

  function chooseWorld(name: string) {
    setWorldName(name);
    setParams(defaultParams(worlds, name));
    const allowed = worlds.find((w) => w.name === name)?.variants ?? [];
    if (!allowed.includes(variant)) setVariant("baseline");
  }

  function start() {
    const overrides: Record<string, unknown> = {};
    for (const [name, value] of Object.entries(mechanisms)) {
      if (value === AS_VARIANT) continue;
      overrides[`mechanisms.${name}`] = value === "true" ? true : value === "false" ? false : value;
    }
    // Only parameters that differ from the world's own go into the run's overrides.
    for (const [key, value] of Object.entries(chosen?.generator ?? {})) {
      if (key === "name" || params[key] === String(value)) continue;
      overrides[`generator.${key}`] = typeof value === "number" ? Number(params[key]) : params[key];
    }
    onStart(
      { seed: Number(seedText), ticks: Number(ticksText), scenario: worldName, variant, overrides, label },
      compare && canCompare,
    );
  }

  return (
    <div className="dialog-backdrop" onClick={onCancel}>
      <div className="dialog" onClick={(e) => e.stopPropagation()}>
        <div className="dialog-head">
          <h2>New run</h2>
          <p>Computed on the server and stored; it plays while it computes.</p>
        </div>
        <div className="dialog-body">
          <label className="field">
            <span>World</span>
            <select value={worldName} onChange={(e) => chooseWorld(e.target.value)}>
              {worlds.map((w) => (
                <option key={w.name} value={w.name}>
                  {w.title} — {w.description}
                </option>
              ))}
            </select>
          </label>
          {chosen?.generator && (
            <div className="field">
              <span>
                Map parameters (generator <code>{String(chosen.generator.name)}</code>)
              </span>
              <div className="mechanism-grid">
                {Object.keys(chosen.generator)
                  .filter((key) => key !== "name")
                  .map((key) => (
                    <label key={key}>
                      {key}
                      <input
                        aria-label={key}
                        value={params[key] ?? ""}
                        onChange={(e) => setParams({ ...params, [key]: e.target.value })}
                      />
                    </label>
                  ))}
              </div>
            </div>
          )}
          <div className="field-row">
            <label className="field">
              <span>Seed</span>
              <input value={seedText} onChange={(e) => setSeedText(e.target.value)} />
            </label>
            <label className="field">
              <span>Ticks</span>
              <input value={ticksText} onChange={(e) => setTicksText(e.target.value)} />
            </label>
          </div>
          <label className="field">
            <span>Variant</span>
            <select value={variant} onChange={(e) => setVariant(e.target.value)}>
              {variants.map(([name, description]) => (
                <option key={name} value={name}>
                  {name} — {description}
                </option>
              ))}
            </select>
          </label>
          <div className="field">
            <span>Mechanisms (leave on "as variant" unless you want to change one)</span>
            <div className="mechanism-grid">
              {Object.entries(scenario.mechanisms).map(([name, base]) => {
                const choices =
                  typeof base === "boolean" ? ["true", "false"] : (scenario.mechanism_choices[name] ?? [String(base)]);
                return (
                  <label key={name}>
                    {name}
                    <select
                      aria-label={name}
                      value={mechanisms[name] ?? AS_VARIANT}
                      onChange={(e) => setMechanisms({ ...mechanisms, [name]: e.target.value })}
                    >
                      <option value={AS_VARIANT}>as variant</option>
                      {choices.map((choice) => (
                        <option key={choice} value={choice}>
                          {choice === "true" ? "on" : choice === "false" ? "off" : choice}
                        </option>
                      ))}
                    </select>
                  </label>
                );
              })}
            </div>
          </div>
          <label className="field">
            <span>Label</span>
            <input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="optional note" />
          </label>
        </div>
        <div className="dialog-foot">
          <label className="check">
            <input
              type="checkbox"
              checked={compare && canCompare}
              disabled={!canCompare}
              onChange={(e) => setCompare(e.target.checked)}
            />
            open it next to the current run
          </label>
          <div className="buttons">
            <button className="ghost" onClick={onCancel}>
              Cancel
            </button>
            <button className="primary" onClick={start}>
              Start run
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

/** A world's generator parameters as editable text (empty for written-out maps). */
function defaultParams(worlds: WorldInfo[], name: string): Record<string, string> {
  const generator = worlds.find((w) => w.name === name)?.generator ?? {};
  return Object.fromEntries(Object.entries(generator).map(([key, value]) => [key, String(value)]));
}
