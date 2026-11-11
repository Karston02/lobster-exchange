import type { PointerEvent } from "react";
import type { Drawing } from "./types";

export interface Pixel {
  x: number;
  y: number;
}

/** Which part of a drawing the pointer grabbed: one of its points, or the whole thing. */
export type Part = number | "all";

interface Props {
  drawing: Drawing;
  pixels: (Pixel | null)[]; // where each point is on screen
  width: number;
  selected: boolean;
  decimals: number;
  onGrab: (event: PointerEvent, drawing: Drawing, part: Part) => void;
}

/** One drawing in SVG: the visible line, a wider invisible line that's easy to
 *  click, and drag handles when it's selected. */
export function Shape({ drawing, pixels, width, selected, decimals, onGrab }: Props) {
  const grab = (part: Part) => (event: PointerEvent) => onGrab(event, drawing, part);
  const handles = selected ? pixels : [];
  const cls = `drawing${selected ? " selected" : ""}`;

  if (drawing.kind === "hline") {
    const y = pixels[0]?.y;
    if (y == null) return null;
    return (
      <g className={cls}>
        <line className="hit" x1={0} y1={y} x2={width} y2={y} onPointerDown={grab(0)} />
        <line className="stroke" x1={0} y1={y} x2={width} y2={y} />
        <text className="price-tag num" x={width - 6} y={y - 6} textAnchor="end">
          {drawing.points[0].price.toFixed(decimals)}
        </text>
      </g>
    );
  }

  const [a, b] = pixels;
  if (!a || !b) return null;
  return (
    <g className={cls}>
      <line className="hit" x1={a.x} y1={a.y} x2={b.x} y2={b.y} onPointerDown={grab("all")} />
      <line className="stroke" x1={a.x} y1={a.y} x2={b.x} y2={b.y} />
      {handles.map((p, i) => p && <circle key={i} className="handle" cx={p.x} cy={p.y} r={5} onPointerDown={grab(i)} />)}
    </g>
  );
}
