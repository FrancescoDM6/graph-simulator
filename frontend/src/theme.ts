// The few interface colours that JavaScript needs (figure backgrounds, text in exported
// figures). They mirror the tokens at the top of styles.css; change both together.
export const THEME = {
  canvas: "#0b0d10", // --bg-0: the graph canvas and chart backgrounds
  panel: "#111418", // --bg-1
  text: "#e6e8ec", // --text
  text2: "#a3a9b5", // --text-2
  text3: "#6b7280", // --text-3
  line: "#22272f", // --line
  danger: "#f06a6a", // --danger
  warning: "#e8a54b", // --warning (droughts)
  good: "#6fcf8e", // --good
};

/** Background of exported figures: the same as on screen. */
export const FIGURE_BACKGROUND = THEME.canvas;
/** Text colour of captions and titles in exported figures. */
export const FIGURE_TEXT = THEME.text;
