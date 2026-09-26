import { useState } from "react";
import { downloadCsv, downloadPng, downloadSvg, type Figure, withMetadata } from "./export";
import { DownloadIcon } from "./icons";

interface Props {
  stem: string; // file name without extension, e.g. "run834_seed4_baseline_timeline"
  title: string; // what the figure shows (written into the file)
  description: string; // which run / experiment / tick it came from (written into the file)
  figure?: () => Figure | null; // omit for data-only exports
  rows?: () => (string | number | boolean | null | undefined)[][]; // CSV, first row = headers
}

/** A download button offering SVG, PNG (2x, 4x) and CSV of what a chart shows. */
export function ExportMenu({ stem, title, description, figure, rows }: Props) {
  const [open, setOpen] = useState(false);
  const [error, setError] = useState("");

  async function run(action: () => void | Promise<void>) {
    setOpen(false);
    try {
      await action();
    } catch (e) {
      setError(String(e));
    }
  }
  const labelled = () => {
    const f = figure?.();
    return f ? withMetadata(f, title, description) : null;
  };

  return (
    <span className="export-menu">
      <button className="ghost icon-button small export-button" title="export this figure" onClick={() => setOpen(!open)}>
        <DownloadIcon />
      </button>
      {open && (
        <span className="popover export-options" onMouseLeave={() => setOpen(false)}>
          {figure && (
            <>
              <button onClick={() => run(() => { const f = labelled(); if (f) downloadSvg(f, stem); })}>SVG</button>
              <button onClick={() => run(async () => { const f = labelled(); if (f) await downloadPng(f, stem, 2); })}>PNG 2×</button>
              <button onClick={() => run(async () => { const f = labelled(); if (f) await downloadPng(f, stem, 4); })}>PNG 4×</button>
            </>
          )}
          {rows && <button onClick={() => run(() => downloadCsv(rows(), stem))}>CSV</button>}
        </span>
      )}
      {error && (
        <span className="error small" onClick={() => setError("")}>
          {error}
        </span>
      )}
    </span>
  );
}
