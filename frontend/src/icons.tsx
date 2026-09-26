// A handful of line icons (16 × 16, drawn with the current text colour), so the interface needs
// no icon library. Each is a few SVG path commands.
import type { ReactNode } from "react";

function Icon({ children, size = 16 }: { children: ReactNode; size?: number }) {
  return (
    <svg
      className="icon"
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {children}
    </svg>
  );
}

export const PlayIcon = () => (
  <Icon>
    <path d="M5 3.5v9l7-4.5z" fill="currentColor" />
  </Icon>
);
export const PauseIcon = () => (
  <Icon>
    <path d="M5.5 3.5v9M10.5 3.5v9" strokeWidth={2} />
  </Icon>
);
export const StepBackIcon = () => (
  <Icon>
    <path d="M4 3.5v9M12 3.5 6.5 8l5.5 4.5z" />
  </Icon>
);
export const StepForwardIcon = () => (
  <Icon>
    <path d="M12 3.5v9M4 3.5 9.5 8 4 12.5z" />
  </Icon>
);
export const DownloadIcon = () => (
  <Icon>
    <path d="M8 2.5v8M4.5 7 8 10.5 11.5 7M3 13.5h10" />
  </Icon>
);
export const CloseIcon = () => (
  <Icon>
    <path d="M4 4l8 8M12 4l-8 8" />
  </Icon>
);
export const BackIcon = () => (
  <Icon>
    <path d="M10 3.5 5.5 8l4.5 4.5" />
  </Icon>
);
export const ChevronIcon = ({ up = false }: { up?: boolean }) => (
  <Icon size={12}>
    <path d={up ? "M4 10l4-4 4 4" : "M4 6l4 4 4-4"} />
  </Icon>
);
export const FitIcon = () => (
  <Icon>
    <path d="M2.5 6V2.5H6M10 2.5h3.5V6M13.5 10v3.5H10M6 13.5H2.5V10" />
  </Icon>
);
export const PlusIcon = () => (
  <Icon>
    <path d="M8 3.5v9M3.5 8h9" />
  </Icon>
);
export const MinusIcon = () => (
  <Icon>
    <path d="M3.5 8h9" />
  </Icon>
);
export const SidebarIcon = () => (
  <Icon>
    <rect x="2" y="3" width="12" height="10" rx="1.5" />
    <path d="M10 3v10" />
  </Icon>
);
/** The app's mark: three linked nodes. */
export const LogoIcon = () => (
  <Icon size={18}>
    <path d="M4 11.5 8 4.5l4 7z" strokeWidth={1.2} opacity={0.6} />
    <circle cx="4" cy="11.5" r="2" fill="#4e79a7" stroke="none" />
    <circle cx="8" cy="4.5" r="2" fill="#e15759" stroke="none" />
    <circle cx="12" cy="11.5" r="2" fill="#59a14f" stroke="none" />
  </Icon>
);
