import type { ShapeProps } from "../Shape";

/** Words on the chart. Drag them to move; double-click to edit. */
export function TextNote({ drawing, pixels, grab }: ShapeProps) {
  const { x, y } = pixels[0];
  return (
    <text className="note" x={x} y={y} onPointerDown={grab("all")}>
      {drawing.text || "Text"}
    </text>
  );
}
