import { useEffect, useRef, useState } from "react";
import { applyTick, PERIOD_S, type Bar, type Tick, type Timeframe } from "./bars";
import { Legend } from "./Legend";
import { createCandleChart, type CandleChart as Chart } from "./lightweight";
import { useTicks } from "./useTicks";

interface Props {
  symbol: string;
  timeframe: Timeframe;
  bars: Bar[];
  intraday: boolean;
  decimals: number;
}

/** The chart canvas plus the OHLC legend. The chart is made once, fed the
 *  history, then kept current: each live trade updates the last candle. */
export function CandleChart({ symbol, timeframe, bars, intraday, decimals }: Props) {
  const box = useRef<HTMLDivElement>(null);
  const chart = useRef<Chart | null>(null);
  const last = useRef<Bar | null>(null);
  const [latest, setLatest] = useState<Bar | null>(null);
  const [hovered, setHovered] = useState<Bar | null>(null);

  useEffect(() => {
    const made = createCandleChart(box.current!, setHovered);
    chart.current = made;
    return () => {
      made.destroy();
      chart.current = null;
    };
  }, []);

  useEffect(() => {
    chart.current?.setBars(bars, intraday, decimals);
    last.current = bars[bars.length - 1] ?? null;
    setLatest(last.current);
    setHovered(null);
  }, [bars, intraday, decimals]);

  useTicks(symbol, (tick: Tick) => {
    if (!last.current || tick.symbol !== symbol) return; // history not loaded yet
    const next = applyTick(last.current, tick, PERIOD_S[timeframe]);
    if (!next) return;
    chart.current?.updateBar(next);
    last.current = next;
    setLatest(next);
  });

  const shown = hovered ?? latest;
  return (
    <div className="chart-area">
      <div ref={box} className="chart-canvas" />
      {shown && <Legend symbol={symbol} bar={shown} decimals={decimals} />}
    </div>
  );
}
