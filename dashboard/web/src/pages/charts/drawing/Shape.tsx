import type { PointerEvent } from "react";
import type { Pixel } from "./geometry";
import { Channel, Rect } from "./shapes/Areas";
import { Fib } from "./shapes/Fib";
import { HLine, Ray, Trend } from "./shapes/Lines";
import { TextNote } from "./shapes/TextNote";
import type { Drawing } from "./types";

/** Which part of a drawing the pointer grabbed: one of its points, or the whole thing. */
export type Part = number | "all";

/** What every shape gets: where its points are on screen, and how to report a grab. */
export interface ShapeProps {
  drawing: Drawing;
  pixels: Pixel[]; // one per point, already on screen
  width: number;
  height: number;
  decimals: number;
  grab: (part: Part) => (event: PointerEvent) => void;
}

interface Props extends Omit<ShapeProps, "pixels"> {
  pixels: (Pixel | null)[];
  selected: boolean;
  onEdit: (drawing: Drawing) => void;
}

const SHAPES = { hline: HLine, trend: Trend, ray: Ray, rect: Rect, fib: Fib, channel: Channel, text: TextNote };

/** One drawing: the right shape for its kind, plus drag handles when it's selected. */
export function Shape({ drawing, pixels, selected, onEdit, ...rest }: Props) {
  if (pixels.some((p) => p === null)) return null; // a point is off the chart (no bars there yet)
  const on = pixels as Pixel[];
  const Kind = SHAPES[drawing.kind];
  const cls = `drawing${selected ? " selected" : ""}${drawing.locked ? " locked" : ""}`;
  // An hline's single handle sits mid-screen; text has no handles (drag the words)
  const handles = !selected || drawing.kind === "text" ? [] : drawing.kind === "hline" ? [{ x: rest.width / 2, y: on[0].y }] : on;
  return (
    <g className={cls} onDoubleClick={() => drawing.kind === "text" && onEdit(drawing)}>
      <Kind drawing={drawing} pixels={on} {...rest} />
      {handles.map((p, i) => (
        <circle key={i} className="handle" cx={p.x} cy={p.y} r={5} onPointerDown={rest.grab(i)} />
      ))}
    </g>
  );
}
