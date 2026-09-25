import { useState } from "react";
import type { Scenario } from "./types";

export interface NewRunRequest {
  seed: number;
  ticks: number;
  variant: string;
  overrides: Record<string, unknown>;
  label: string;
}

interface Props {
  scenario: Scenario;
  seed: number; // defaults: usually the run currently shown, so "same seed, one change" is easy
  ticks: number;
  onCancel: () => void;
  onStart: (request: NewRunRequest, compareWithCurrent: boolean) => void;
}

const AS_VARIANT = ""; // mechanism left as the chosen variant (and scenario.toml) set it

/** Start a new stored run: a seed, a variant from scenario.toml, and optional switches. */
export function NewRunDialog({ scenario, seed, ticks, onCancel, onStart }: Props) {
  const [seedText, setSeedText] = useState(String(seed));
  const [ticksText, setTicksText] = useState(String(ticks));
  const [variant, setVariant] = useState("baseline");
  const [mechanisms, setMechanisms] = useState<Record<string, string>>({});
  const [label, setLabel] = useState("");
  const [compare, setCompare] = useState(true);

  function start() {
    const overrides: Record<string, unknown> = {};
    for (const [name, value] of Object.entries(mechanisms)) {
      if (value === AS_VARIANT) continue;
      overrides[`mechanisms.${name}`] = value === "true" ? true : value === "false" ? false : value;
    }
    onStart({ seed: Number(seedText), ticks: Number(ticksText), variant, overrides, label }, compare);
  }

  return (
    <div className="dialog-backdrop" onClick={onCancel}>
      <div className="dialog" onClick={(e) => e.stopPropagation()}>
        <h2>New run</h2>
        <div className="form-row">
          <label>
            Seed <input value={seedText} onChange={(e) => setSeedText(e.target.value)} size={6} />
          </label>
          <label>
            Ticks <input value={ticksText} onChange={(e) => setTicksText(e.target.value)} size={6} />
          </label>
        </div>
        <label className="form-block">
          Variant
          <select value={variant} onChange={(e) => setVariant(e.target.value)}>
            {Object.entries(scenario.variants).map(([name, description]) => (
              <option key={name} value={name}>
                {name} — {description}
              </option>
            ))}
          </select>
        </label>
        <div className="form-block">
          Mechanisms <span className="muted">(leave on "as variant" unless you want to change one)</span>
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
        <label className="form-block">
          Label <input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="optional note" />
        </label>
        <label className="form-check">
          <input type="checkbox" checked={compare} onChange={(e) => setCompare(e.target.checked)} /> open it next to the
          current run
        </label>
        <div className="dialog-buttons">
          <button onClick={onCancel}>Cancel</button>
          <button className="primary" onClick={start}>
            Start run
          </button>
        </div>
      </div>
    </div>
  );
}
