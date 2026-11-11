import type { ReactNode } from "react";
import type { Tool } from "./types";

interface Props {
  tool: Tool;
  onTool: (tool: Tool) => void;
  canDelete: boolean;
  onDelete: () => void;
}

const ICON = { width: 18, height: 18, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.8 };

const TOOLS: { tool: Tool; label: string; icon: ReactNode }[] = [
  {
    tool: "select",
    label: "Select and move (Esc)",
    icon: (
      <svg {...ICON} aria-hidden="true">
        <path d="M5 3l14 8-6 2-2 6z" />
      </svg>
    ),
  },
  {
    tool: "trend",
    label: "Trend line",
    icon: (
      <svg {...ICON} aria-hidden="true">
        <path d="M4 19L20 5" />
        <circle cx="4" cy="19" r="1.6" />
        <circle cx="20" cy="5" r="1.6" />
      </svg>
    ),
  },
  {
    tool: "hline",
    label: "Horizontal line",
    icon: (
      <svg {...ICON} aria-hidden="true">
        <path d="M3 12h18" />
      </svg>
    ),
  },
];

/** The vertical toolbar on the chart's left. */
export function DrawingTools({ tool, onTool, canDelete, onDelete }: Props) {
  return (
    <div className="drawing-tools" role="toolbar" aria-label="Drawing tools" aria-orientation="vertical">
      {TOOLS.map((t) => (
        <button
          key={t.tool}
          type="button"
          className="icon-button"
          aria-pressed={tool === t.tool}
          aria-label={t.label}
          title={t.label}
          onClick={() => onTool(t.tool)}
        >
          {t.icon}
        </button>
      ))}
      <span className="tools-gap" />
      <button
        type="button"
        className="icon-button"
        aria-label="Delete the selected drawing (Delete)"
        title="Delete the selected drawing (Delete)"
        disabled={!canDelete}
        onClick={onDelete}
      >
        <svg {...ICON} aria-hidden="true">
          <path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3" />
        </svg>
      </button>
    </div>
  );
}
