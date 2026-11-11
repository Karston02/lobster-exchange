import { useEffect, useRef, useState, type PointerEvent } from "react";
import type { CandleChart, Viewport } from "../lightweight";
import { logicalToTime, timeToLogical } from "./coords";
import { Shape, type Part, type Pixel } from "./Shape";
import type { Anchor, Drawing, Tool } from "./types";
import "./drawing.css";

interface Props {
  chart: CandleChart | null;
  times: number[]; // the bars' start times, ascending
  periodS: number;
  decimals: number;
  symbol: string;
  drawings: Drawing[];
  tool: Tool;
  selectedId: string | null;
  onSave: (drawing: Drawing) => void;
  onSelect: (id: string | null) => void;
  onToolDone: () => void;
}

interface Drag {
  original: Drawing;
  part: Part;
  start: Anchor & { logical: number }; // where the pointer went down
  moved: boolean;
}

/** An SVG layer over the chart's plotting area that draws, selects and drags drawings.
 *
 *  It's transparent to the pointer except on drawings, so the chart still pans
 *  and zooms underneath; while a drawing tool is active it takes every click. */
export function DrawingLayer(props: Props) {
  const { chart, times, periodS, drawings, tool, selectedId } = props;
  const svg = useRef<SVGSVGElement>(null);
  const [draft, setDraft] = useState<Drawing | null>(null); // a trend line being drawn
  const [moving, setMoving] = useState<Drawing | null>(null); // a drawing being dragged
  const drag = useRef<Drag | null>(null);
  const view = useViewport(chart);

  // Switching tools (Esc does that too) or symbols abandons a half-drawn line
  useEffect(() => setDraft(null), [tool, props.symbol]);

  if (!view) return null;

  const toPixel = (a: Anchor): Pixel | null => {
    const x = view.logicalToX(timeToLogical(times, periodS, a.time));
    const y = view.priceToY(a.price);
    return x == null || y == null ? null : { x, y };
  };

  const pointerAt = (event: PointerEvent): (Anchor & { logical: number }) | null => {
    const box = svg.current!.getBoundingClientRect();
    const current = chart!.viewport(); // fresh, in case the chart moved this frame
    const logical = current.xToLogical(event.clientX - box.left);
    const price = current.yToPrice(event.clientY - box.top);
    if (logical == null || price == null) return null;
    return { logical, price, time: Math.round(logicalToTime(times, periodS, logical)) };
  };

  // --- drawing something new ---

  function onPointerDown(event: PointerEvent) {
    if (tool === "select") return;
    const at = pointerAt(event);
    if (!at) return;
    const point = { time: at.time, price: at.price };
    if (tool === "hline") {
      finish({ id: crypto.randomUUID(), symbol: props.symbol, kind: "hline", points: [point] });
    } else if (!draft) {
      setDraft({ id: crypto.randomUUID(), symbol: props.symbol, kind: "trend", points: [point, point] });
    } else {
      finish({ ...draft, points: [draft.points[0], point] });
    }
  }

  function finish(drawing: Drawing) {
    setDraft(null);
    props.onSave(drawing);
    props.onSelect(drawing.id);
    props.onToolDone();
  }

  // --- grabbing and dragging ---

  function onGrab(event: PointerEvent, drawing: Drawing, part: Part) {
    if (tool !== "select") return;
    event.stopPropagation();
    props.onSelect(drawing.id);
    const at = pointerAt(event);
    if (!at) return;
    drag.current = { original: drawing, part, start: at, moved: false };
    svg.current!.setPointerCapture(event.pointerId);
    chart!.setInteractive(false); // the chart mustn't pan while a drawing moves
  }

  function onPointerMove(event: PointerEvent) {
    const at = pointerAt(event);
    if (!at) return;
    if (draft) {
      setDraft({ ...draft, points: [draft.points[0], { time: at.time, price: at.price }] });
      return;
    }
    const d = drag.current;
    if (!d) return;
    d.moved = true;
    setMoving(dragged(d, at));
  }

  function onPointerUp(event: PointerEvent) {
    const d = drag.current;
    if (!d) return;
    drag.current = null;
    svg.current!.releasePointerCapture(event.pointerId);
    chart!.setInteractive(true);
    if (d.moved && moving) props.onSave(moving);
    setMoving(null);
  }

  /** Where the drawing is after dragging from `d.start` to `at`. */
  function dragged(d: Drag, at: Anchor & { logical: number }): Drawing {
    const points = d.original.points;
    if (d.part === "all") {
      // Move every point by the same number of bars and dollars
      const bars = at.logical - d.start.logical;
      const dollars = at.price - d.start.price;
      return {
        ...d.original,
        points: points.map((p) => ({
          time: Math.round(logicalToTime(times, periodS, timeToLogical(times, periodS, p.time) + bars)),
          price: p.price + dollars,
        })),
      };
    }
    const index = d.part;
    const moved = d.original.kind === "hline" ? { time: points[0].time, price: at.price } : { time: at.time, price: at.price };
    return { ...d.original, points: points.map((p, i) => (i === index ? moved : p)) };
  }

  const shown = [...drawings.map((d) => (moving && d.id === moving.id ? moving : d)), ...(draft ? [draft] : [])];
  const capturing = tool !== "select" || drag.current !== null;

  return (
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
          selected={d.id === selectedId || d === draft}
          decimals={props.decimals}
          onGrab={onGrab}
        />
      ))}
    </svg>
  );
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
