import { useEffect, useRef, useState } from "react";
import type { Bar } from "./bars";
import { Legend } from "./Legend";
import { createCandleChart, type CandleChart as Chart } from "./lightweight";

interface Props {
  symbol: string;
  bars: Bar[];
  intraday: boolean;
  decimals: number;
}

/** The chart canvas plus the OHLC legend. The chart is made once and fed new bars. */
export function CandleChart({ symbol, bars, intraday, decimals }: Props) {
  const box = useRef<HTMLDivElement>(null);
  const chart = useRef<Chart | null>(null);
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
    setHovered(null);
  }, [bars, intraday, decimals]);

  const shown = hovered ?? bars[bars.length - 1] ?? null;
  return (
    <div className="chart-area">
      <div ref={box} className="chart-canvas" />
      {shown && <Legend symbol={symbol} bar={shown} decimals={decimals} />}
    </div>
  );
}
