// Every call into TradingView's Lightweight Charts lives in this file, so the
// rest of the page never depends on the library's API directly.
// Docs: https://tradingview.github.io/lightweight-charts/ (version 5)

import {
  CandlestickSeries,
  ColorType,
  createChart,
  HistogramSeries,
  type MouseEventParams,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";
import type { Bar } from "./bars";

// The app theme (styles.css); the chart draws on a canvas, so it needs the values
const THEME = {
  bg: "#0e1116",
  text: "#9aa4b2",
  grid: "#151a21", // fainter than the hairlines
  line: "#1b2028",
  up: "#4fd1a1",
  down: "#ff8f6b",
  upVolume: "rgba(79, 209, 161, 0.25)",
  downVolume: "rgba(255, 143, 107, 0.25)",
};

const BARS_IN_VIEW = 150; // how many recent bars to show at first

export interface CandleChart {
  setBars(bars: Bar[], intraday: boolean): void;
  destroy(): void;
}

/** The chart shows times in UTC, so shift each one by your time zone's offset at that moment. */
function chartTime(unixSeconds: number): UTCTimestamp {
  const offsetMinutes = new Date(unixSeconds * 1000).getTimezoneOffset();
  return (unixSeconds - offsetMinutes * 60) as UTCTimestamp;
}

/** Draws candles with volume underneath into `container`, sized to fill it.
 *  `onHover` gets the bar under the crosshair, or null when the pointer leaves. */
export function createCandleChart(container: HTMLElement, onHover: (bar: Bar | null) => void): CandleChart {
  const chart = createChart(container, {
    autoSize: true,
    layout: {
      background: { type: ColorType.Solid, color: THEME.bg },
      textColor: THEME.text,
      fontFamily: "Inter, system-ui, sans-serif",
    },
    grid: { vertLines: { color: THEME.grid }, horzLines: { color: THEME.grid } },
    rightPriceScale: { borderColor: THEME.line },
    timeScale: { borderColor: THEME.line, secondsVisible: false },
  });

  const candles = chart.addSeries(CandlestickSeries, {
    upColor: THEME.up,
    downColor: THEME.down,
    borderVisible: false,
    wickUpColor: THEME.up,
    wickDownColor: THEME.down,
  });
  candles.priceScale().applyOptions({ scaleMargins: { top: 0.08, bottom: 0.25 } });

  // Volume sits on its own hidden scale, in the bottom fifth of the chart
  const volume = chart.addSeries(HistogramSeries, {
    priceScaleId: "volume",
    priceFormat: { type: "volume" },
    lastValueVisible: false,
    priceLineVisible: false,
  });
  chart.priceScale("volume").applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });

  let byTime = new Map<number, Bar>();
  const hover = (param: MouseEventParams<Time>) => {
    onHover(param.time === undefined ? null : (byTime.get(param.time as number) ?? null));
  };
  chart.subscribeCrosshairMove(hover);

  return {
    setBars(bars, intraday) {
      byTime = new Map(bars.map((b) => [chartTime(b.time), b]));
      chart.applyOptions({ timeScale: { timeVisible: intraday } });
      candles.setData(bars.map((b) => ({ time: chartTime(b.time), open: b.open, high: b.high, low: b.low, close: b.close })));
      volume.setData(
        bars.map((b) => ({
          time: chartTime(b.time),
          value: b.volume,
          color: b.close >= b.open ? THEME.upVolume : THEME.downVolume,
        })),
      );
      const n = bars.length;
      chart.timeScale().setVisibleLogicalRange({ from: Math.max(0, n - BARS_IN_VIEW), to: n + 3 });
    },
    destroy() {
      chart.unsubscribeCrosshairMove(hover);
      chart.remove();
    },
  };
}
