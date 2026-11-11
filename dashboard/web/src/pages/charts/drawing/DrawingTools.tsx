import type { ReactNode } from "react";
import { Icons } from "./icons";
import type { Tool } from "./types";

interface Props {
  tool: Tool;
  onTool: (tool: Tool) => void;
  snap: boolean;
  onSnap: (on: boolean) => void;
  selectedLocked: boolean | null; // null: nothing selected
  onLock: () => void;
  onDelete: () => void;
}

const TOOLS: { tool: Tool; label: string }[] = [
  { tool: "select", label: "Select and move (Esc)" },
  { tool: "trend", label: "Trend line" },
  { tool: "ray", label: "Ray" },
  { tool: "hline", label: "Horizontal line" },
  { tool: "channel", label: "Parallel channel (3 clicks)" },
  { tool: "fib", label: "Fibonacci retracement (start of the move, then its end)" },
  { tool: "rect", label: "Rectangle" },
  { tool: "text", label: "Text" },
  { tool: "measure", label: "Measure (not saved)" },
];

/** The vertical toolbar on the chart's left: drawing tools, then snap, lock and delete. */
export function DrawingTools({ tool, onTool, snap, onSnap, selectedLocked, onLock, onDelete }: Props) {
  const nothing = selectedLocked === null;
  return (
    <div className="drawing-tools" role="toolbar" aria-label="Drawing tools" aria-orientation="vertical">
      {TOOLS.map((t) => (
        <ToolButton key={t.tool} label={t.label} pressed={tool === t.tool} onClick={() => onTool(t.tool)}>
          {Icons[t.tool]}
        </ToolButton>
      ))}
      <span className="tools-gap" />
      <ToolButton label="Snap to candle open, high, low or close" pressed={snap} onClick={() => onSnap(!snap)}>
        {Icons.snap}
      </ToolButton>
      <ToolButton
        label={selectedLocked ? "Unlock the selected drawing" : "Lock the selected drawing"}
        pressed={selectedLocked === true}
        disabled={nothing}
        onClick={onLock}
      >
        {Icons.lock}
      </ToolButton>
      <ToolButton
        label="Delete the selected drawing (Delete)"
        disabled={nothing || selectedLocked === true}
        onClick={onDelete}
      >
        {Icons.trash}
      </ToolButton>
    </div>
  );
}

interface ButtonProps {
  label: string;
  pressed?: boolean;
  disabled?: boolean;
  onClick: () => void;
  children: ReactNode;
}

function ToolButton({ label, pressed, disabled, onClick, children }: ButtonProps) {
  return (
    <button
      type="button"
      className="icon-button"
      aria-pressed={pressed}
      aria-label={label}
      title={label}
      disabled={disabled}
      onClick={onClick}
    >
      {children}
    </button>
  );
}
