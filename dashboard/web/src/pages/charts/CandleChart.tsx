import { useEffect, useRef, useState, type PointerEvent } from "react";
import { applyTick, PERIOD_S, type Bar, type Tick, type Timeframe } from "./bars";
import { DrawingLayer } from "./drawing/DrawingLayer";
import type { Drawing, Tool } from "./drawing/types";
import { Legend } from "./Legend";
import { createCandleChart, type CandleChart as Chart } from "./lightweight";
import { useTicks } from "./useTicks";

/** What the drawing layer needs from the page. */
export interface DrawingControls {
  drawings: Drawing[];
  tool: Tool;
  snap: boolean;
  selectedId: string | null;
  onSave: (drawing: Drawing) => void;
  onSelect: (id: string | null) => void;
  onToolDone: () => void;
}

interface Props {
  symbol: string;
  timeframe: Timeframe;
  bars: Bar[];
  intraday: boolean;
  decimals: number;
  drawing: DrawingControls;
}

/** The chart canvas, the drawings over it, and the OHLC legend. The chart is
 *  made once, fed the history, then kept current: each live trade updates the
 *  last candle. */
export function CandleChart({ symbol, timeframe, bars, intraday, decimals, drawing }: Props) {
  const box = useRef<HTMLDivElement>(null);
  const [chart, setChart] = useState<Chart | null>(null);
  const last = useRef<Bar | null>(null);
  const [series, setSeries] = useState<Bar[]>([]); // the bars on screen, live last bar included
  const [latest, setLatest] = useState<Bar | null>(null);
  const [hovered, setHovered] = useState<Bar | null>(null);

  useEffect(() => {
    const made = createCandleChart(box.current!, setHovered);
    setChart(made);
    return () => {
      made.destroy();
      setChart(null);
    };
  }, []);

  useEffect(() => {
    chart?.setBars(bars, intraday, decimals);
    last.current = bars[bars.length - 1] ?? null;
    setSeries(bars);
    setLatest(last.current);
    setHovered(null);
  }, [chart, bars, intraday, decimals]);

  useTicks(symbol, (tick: Tick) => {
    if (!last.current || tick.symbol !== symbol) return; // history not loaded yet
    const next = applyTick(last.current, tick, PERIOD_S[timeframe]);
    if (!next) return;
    chart?.updateBar(next);
    const isNew = next.time !== last.current.time;
    setSeries((old) => (isNew ? [...old, next] : [...old.slice(0, -1), next]));
    last.current = next;
    setLatest(next);
  });

  // A click on empty chart (not on a drawing) clears the selection
  function onPointerDown(event: PointerEvent) {
    if (drawing.tool === "select" && !(event.target as Element).closest(".drawing")) drawing.onSelect(null);
  }

  const shown = hovered ?? latest;
  return (
    <div className="chart-area" onPointerDown={onPointerDown}>
      <div ref={box} className="chart-canvas" />
      <DrawingLayer
        chart={chart}
        bars={series}
        periodS={PERIOD_S[timeframe]}
        decimals={decimals}
        symbol={symbol}
        {...drawing}
      />
      {shown && <Legend symbol={symbol} bar={shown} decimals={decimals} />}
    </div>
  );
}
