// Exporting figures: SVG (vector, for papers), PNG (raster, at 2x or 4x) and CSV (the numbers
// behind a chart). Every file carries metadata saying which run, tick and settings it shows.
import type { RunInfo } from "./types";

export interface Figure {
  svg: string; // a complete <svg> document
  width: number;
  height: number;
}

// Style properties that make a chart look the same outside the page's stylesheet.
const INLINED_STYLES = [
  "fill",
  "fill-opacity",
  "stroke",
  "stroke-width",
  "stroke-opacity",
  "stroke-dasharray",
  "opacity",
  "font-size",
  "font-family",
  "font-weight",
  "font-style",
  "text-anchor",
  "visibility",
];

/** An on-page <svg> as a standalone SVG document, with its CSS styles written into it. */
export function figureFromElement(svg: SVGSVGElement, background: string): Figure {
  const clone = svg.cloneNode(true) as SVGSVGElement;
  const originals = svg.querySelectorAll("*");
  clone.querySelectorAll("*").forEach((element, i) => {
    const computed = getComputedStyle(originals[i]);
    const style = INLINED_STYLES.map((name) => `${name}:${computed.getPropertyValue(name)}`).join(";");
    element.setAttribute("style", style);
    element.removeAttribute("class");
  });
  const width = svg.width.baseVal.value;
  const height = svg.height.baseVal.value;
  clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  clone.setAttribute("width", String(width));
  clone.setAttribute("height", String(height));
  const backdrop = document.createElementNS("http://www.w3.org/2000/svg", "rect");
  backdrop.setAttribute("width", "100%");
  backdrop.setAttribute("height", "100%");
  backdrop.setAttribute("fill", background);
  clone.insertBefore(backdrop, clone.firstChild);
  return { svg: new XMLSerializer().serializeToString(clone), width, height };
}

/** Figures stacked vertically (or side by side), each with an optional title, plus a caption. */
export function composeFigure(
  panels: (Figure & { title?: string })[],
  caption: string,
  options: { direction?: "down" | "across"; background: string; textColor: string },
): Figure {
  const titleHeight = panels.some((p) => p.title) ? 20 : 0;
  const gap = 12;
  const across = options.direction === "across";
  let x = 0;
  let y = 0;
  const parts: string[] = [];
  for (const panel of panels) {
    if (panel.title) {
      parts.push(
        `<text x="${x + 4}" y="${y + 14}" font-size="13" font-family="sans-serif" fill="${options.textColor}">${escapeXml(panel.title)}</text>`,
      );
    }
    parts.push(
      `<svg x="${x}" y="${y + titleHeight}" width="${panel.width}" height="${panel.height}">${inner(panel.svg)}</svg>`,
    );
    if (across) x += panel.width + gap;
    else y += panel.height + titleHeight + gap;
  }
  const width = across ? x - gap : Math.max(...panels.map((p) => p.width));
  const contentHeight = across ? Math.max(...panels.map((p) => p.height)) + titleHeight : y - gap;
  const lines = wrap(caption, Math.max(40, Math.floor(width / CHAR_WIDTH)));
  const height = contentHeight + 10 + lines.length * 15;
  lines.forEach((line, i) =>
    parts.push(
      `<text x="4" y="${contentHeight + 22 + i * 15}" font-size="11" font-family="sans-serif" fill="${options.textColor}">${escapeXml(line)}</text>`,
    ),
  );
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}">` +
    `<rect width="100%" height="100%" fill="${options.background}"/>${parts.join("")}</svg>`;
  return { svg, width, height };
}

/** Adds <title> and <desc> (what the figure shows, and exactly which run it came from). */
export function withMetadata(figure: Figure, title: string, description: string): Figure {
  const meta = `<title>${escapeXml(title)}</title><desc>${escapeXml(description)}</desc>`;
  return { ...figure, svg: figure.svg.replace(/(<svg[^>]*>)/, `$1${meta}`) };
}

/** "run 834 (world three_towns, seed 4, variant no_gifting, 800 ticks, code 530ac6c, config 1a4b…)" */
export function runDescription(run: RunInfo | undefined): string {
  if (!run) return "";
  const overrides = Object.entries(run.overrides)
    .map(([k, v]) => `${k}=${v}`)
    .join(", ");
  return (
    `run ${run.id} (world ${run.scenario}, seed ${run.seed}, variant ${run.variant}${overrides ? `, ${overrides}` : ""}, ` +
    `${run.ticks} ticks, code ${run.code_version}, config ${run.config_hash}` +
    (run.parent_run !== null
      ? `; a branch of run ${run.parent_run} at tick ${run.branch_tick}: ${run.interventions
          .filter((i) => i.tick === run.branch_tick)
          .map((i) => JSON.stringify(i))
          .join(" ")}`
      : "") +
    ")"
  );
}

/** "run834_three_towns_seed4_no_gifting_t250" */
export function fileStem(run: RunInfo | undefined, ...parts: (string | number | undefined)[]): string {
  const base = run ? [`run${run.id}`, run.scenario, `seed${run.seed}`, run.variant] : [];
  return [...base, ...parts.filter((p) => p !== undefined && p !== "")].join("_").replace(/[^A-Za-z0-9_.-]+/g, "-");
}

export function downloadSvg(figure: Figure, stem: string) {
  download(new Blob([figure.svg], { type: "image/svg+xml" }), `${stem}.svg`);
}

export async function downloadPng(figure: Figure, stem: string, scale: number) {
  const image = new Image();
  const url = URL.createObjectURL(new Blob([figure.svg], { type: "image/svg+xml" }));
  try {
    image.src = url;
    await image.decode();
    const canvas = document.createElement("canvas");
    canvas.width = Math.ceil(figure.width * scale);
    canvas.height = Math.ceil(figure.height * scale);
    const context = canvas.getContext("2d")!;
    context.scale(scale, scale);
    context.drawImage(image, 0, 0, figure.width, figure.height);
    const blob = await new Promise<Blob>((resolve, reject) =>
      canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("PNG encoding failed"))), "image/png"),
    );
    download(blob, `${stem}.png`);
  } finally {
    URL.revokeObjectURL(url);
  }
}

/** Rows to CSV text (values containing commas, quotes or newlines are quoted). */
export function toCsv(rows: (string | number | boolean | null | undefined)[][]): string {
  const cell = (value: unknown) => {
    const text = value === null || value === undefined ? "" : String(value);
    return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  };
  return rows.map((row) => row.map(cell).join(",")).join("\n") + "\n";
}

export function downloadCsv(rows: (string | number | boolean | null | undefined)[][], stem: string) {
  download(new Blob([toCsv(rows)], { type: "text/csv" }), `${stem}.csv`);
}

function download(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

const CHAR_WIDTH = 6.2; // approximate width of an 11px sans-serif character, for wrapping

/** Splits text into lines of at most `limit` characters, at spaces (keeps existing newlines). */
function wrap(text: string, limit: number): string[] {
  const lines: string[] = [];
  for (const paragraph of text.split("\n")) {
    let line = "";
    for (const word of paragraph.split(" ")) {
      if (line && line.length + 1 + word.length > limit) {
        lines.push(line);
        line = word;
      } else {
        line = line ? `${line} ${word}` : word;
      }
    }
    lines.push(line);
  }
  return lines;
}

function inner(svgDocument: string): string {
  return svgDocument.replace(/^[\s\S]*?<svg[^>]*>/, "").replace(/<\/svg>\s*$/, "");
}

function escapeXml(text: string): string {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
