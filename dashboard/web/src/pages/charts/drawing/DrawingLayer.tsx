import { useEffect, useMemo, useRef, useState, type PointerEvent } from "react";
import type { Bar } from "../bars";
import type { CandleChart, Viewport } from "../lightweight";
import { logicalToTime, timeToLogical } from "./coords";
import { measure, type Pixel } from "./geometry";
import { MeasureBox } from "./MeasureBox";
import { Shape, type Part } from "./Shape";
import { snapToBar } from "./snap";
import { TextEditor } from "./TextEditor";
import { CLICKS, type Anchor, type Drawing, type DrawingKind, type Tool } from "./types";
import "./drawing.css";

interface Props {
  chart: CandleChart | null;
  bars: Bar[]; // ascending, including the live last bar
  periodS: number;
  decimals: number;
  symbol: string;
  drawings: Drawing[];
  tool: Tool;
  snap: boolean;
  selectedId: string | null;
  onSave: (drawing: Drawing) => void;
  onSelect: (id: string | null) => void;
  onToolDone: () => void;
}

/** A point under the pointer: chart position plus its bar index. */
type At = Anchor & { logical: number };

interface Drag {
  original: Drawing;
  part: Part;
  start: At;
}

/** Something being drawn: its points so far, the last one following the pointer. */
interface Draft {
  kind: DrawingKind | "measure";
  points: At[];
}

/** An SVG layer over the chart's plotting area that draws, selects and drags drawings.
 *
 *  It's transparent to the pointer except on drawings, so the chart still pans
 *  and zooms underneath; while a drawing tool is active it takes every click. */
export function DrawingLayer(props: Props) {
  const { chart, bars, periodS, tool, selectedId } = props;
  const times = useMemo(() => bars.map((b) => b.time), [bars]);
  const svg = useRef<SVGSVGElement>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [measured, setMeasured] = useState<At[] | null>(null); // the last measurement, until the next click
  const [moving, setMoving] = useState<Drawing | null>(null); // a drawing being dragged
  const [editing, setEditing] = useState<Drawing | null>(null); // a text drawing being written
  const drag = useRef<Drag | null>(null);
  const view = useViewport(chart);

  // Switching tools (Esc does that too) or symbols abandons anything half-drawn
  useEffect(() => {
    setDraft(null);
    setEditing(null);
  }, [tool, props.symbol]);

  // A measurement stays up until the next click anywhere
  useEffect(() => {
    if (!measured) return;
    const clear = () => setMeasured(null);
    window.addEventListener("pointerdown", clear, { once: true });
    return () => window.removeEventListener("pointerdown", clear);
  }, [measured]);

  if (!view) return null;

  const toPixel = (a: Anchor): Pixel | null => {
    const x = view.logicalToX(timeToLogical(times, periodS, a.time));
    const y = view.priceToY(a.price);
    return x == null || y == null ? null : { x, y };
  };

  const pointerAt = (event: PointerEvent): At | null => {
    const box = svg.current!.getBoundingClientRect();
    const current = chart!.viewport(); // fresh, in case the chart moved this frame
    const x = event.clientX - box.left;
    const y = event.clientY - box.top;
    let logical = current.xToLogical(x);
    let price = current.yToPrice(y);
    if (logical == null || price == null) return null;
    if (props.snap) ({ logical, price } = snapToBar(logical, price, y, bars, current));
    return { logical, price, time: Math.round(logicalToTime(times, periodS, logical)) };
  };

  // --- drawing something new ---

  function onPointerDown(event: PointerEvent) {
    if (tool === "select" || editing) return;
    const at = pointerAt(event);
    if (!at) return;
    const points = draft ? [...draft.points.slice(0, -1), at] : [at]; // fix the point that was following
    if (points.length < CLICKS[tool]) {
      setDraft({ kind: tool, points: [...points, at] }); // and start a new following point
      return;
    }
    setDraft(null);
    props.onToolDone();
    if (tool === "measure") {
      setMeasured(points);
      return;
    }
    const drawing = newDrawing(tool, points);
    if (tool === "text") setEditing(drawing); // saved once it has words
    else {
      props.onSave(drawing);
      props.onSelect(drawing.id);
    }
  }

  function newDrawing(kind: DrawingKind, points: At[]): Drawing {
    return {
      id: crypto.randomUUID(),
      symbol: props.symbol,
      kind,
      points: points.map((p) => ({ time: p.time, price: p.price })),
      text: "",
      locked: false,
    };
  }

  function onTextDone(text: string | null) {
    const drawing = editing!;
    setEditing(null);
    if (text === null || !text.trim()) return; // cancelled, or nothing written: nothing to keep
    if (text !== drawing.text) props.onSave({ ...drawing, text: text.trim() });
    props.onSelect(drawing.id);
  }

  // --- grabbing and dragging ---

  const grab = (drawing: Drawing) => (part: Part) => (event: PointerEvent) => {
    if (tool !== "select") return;
    event.stopPropagation();
    props.onSelect(drawing.id);
    if (drawing.locked) return; // selectable (to unlock), but it doesn't move
    const at = pointerAt(event);
    if (!at) return;
    drag.current = { original: drawing, part, start: at };
    svg.current!.setPointerCapture(event.pointerId);
    chart!.setInteractive(false); // the chart mustn't pan while a drawing moves
  };

  function onPointerMove(event: PointerEvent) {
    if (!draft && !drag.current) return;
    const at = pointerAt(event);
    if (!at) return;
    if (draft) setDraft({ ...draft, points: [...draft.points.slice(0, -1), at] });
    else setMoving(dragged(drag.current!, at));
  }

  function onPointerUp(event: PointerEvent) {
    if (!drag.current) return;
    drag.current = null;
    svg.current!.releasePointerCapture(event.pointerId);
    chart!.setInteractive(true);
    if (moving) props.onSave(moving);
    setMoving(null);
  }

  /** Where the drawing is after dragging from `d.start` to `at`. */
  function dragged(d: Drag, at: At): Drawing {
    const points = d.original.points;
    if (d.part === "all") {
      // Move every point by the same number of bars and dollars
      const shift = at.logical - d.start.logical;
      const dollars = at.price - d.start.price;
      return {
        ...d.original,
        points: points.map((p) => ({
          time: Math.round(logicalToTime(times, periodS, timeToLogical(times, periodS, p.time) + shift)),
          price: p.price + dollars,
        })),
      };
    }
    const index = d.part;
    const moved = d.original.kind === "hline" ? { time: points[0].time, price: at.price } : { time: at.time, price: at.price };
    return { ...d.original, points: points.map((p, i) => (i === index ? moved : p)) };
  }

  // --- what's on screen ---

  const draftDrawing = draft && draft.kind !== "measure" ? { ...newDrawing(draft.kind, draft.points), id: "draft" } : null;
  const shown = [
    ...props.drawings.filter((d) => d.id !== editing?.id).map((d) => (moving && d.id === moving.id ? moving : d)),
    ...(draftDrawing ? [draftDrawing] : []),
  ];
  const measuring = draft?.kind === "measure" ? draft.points : measured;
  const capturing = tool !== "select" || drag.current !== null;
  const editAt = editing ? toPixel(editing.points[0]) : null;

  return (
    <>
      <svg
        ref={svg}
        className={`drawing-layer${capturing ? " capturing" : ""}`}
        width={view.width}
        height={view.height}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
      >
        {shown.map((d) => (
          <Shape
            key={d.id}
            drawing={d}
            pixels={d.points.map(toPixel)}
            width={view.width}
            height={view.height}
            decimals={props.decimals}
            selected={d.id === selectedId || d === draftDrawing}
            grab={grab(d)}
            onEdit={setEditing}
          />
        ))}
        {measuring && measuring.length === 2 && (
          <MeasurePair points={measuring} toPixel={toPixel} decimals={props.decimals} />
        )}
      </svg>
      {editing && editAt && <TextEditor key={editing.id} at={editAt} initial={editing.text} onDone={onTextDone} />}
    </>
  );
}

function MeasurePair({ points, toPixel, decimals }: { points: At[]; toPixel: (a: Anchor) => Pixel | null; decimals: number }) {
  const [a, b] = points.map(toPixel);
  if (!a || !b) return null;
  return <MeasureBox a={a} b={b} result={measure(points[0], points[1])} decimals={decimals} />;
}

/** The chart's viewport, re-read every animation frame. React only re-renders
 *  when it actually changed: the chart's mappings are straight lines, so two
 *  sample points on each axis plus the size describe them completely. */
function useViewport(chart: CandleChart | null): Viewport | null {
  const [view, setView] = useState<Viewport | null>(null);
  const signature = useRef("");

  useEffect(() => {
    if (!chart) return;
    let frame = 0;
    const check = () => {
      const v = chart.viewport();
      const sig = [v.width, v.height, v.logicalToX(0), v.logicalToX(1), v.priceToY(0), v.priceToY(1)].join();
      if (sig !== signature.current) {
        signature.current = sig;
        setView(v);
      }
      frame = requestAnimationFrame(check);
    };
    check();
    return () => cancelAnimationFrame(frame);
  }, [chart]);

  return view;
}
