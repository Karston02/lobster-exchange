// Every call into TradingView's Lightweight Charts lives in this file, so the
// rest of the page never depends on the library's API directly.
// Docs: https://tradingview.github.io/lightweight-charts/ (version 5)

import {
  CandlestickSeries,
  ColorType,
  createChart,
  CrosshairMode,
  HistogramSeries,
  TickMarkType,
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
  crosshair: "#6b7585",
  label: "#1b2330", // background of the price and time tags on the axes
};

const BARS_IN_VIEW = 150; // how many recent bars to show at first

const candlePoint = (b: Bar) => ({ time: b.time as UTCTimestamp, open: b.open, high: b.high, low: b.low, close: b.close });
const volumePoint = (b: Bar) => ({
  time: b.time as UTCTimestamp,
  value: b.volume,
  color: b.close >= b.open ? THEME.upVolume : THEME.downVolume,
});

export interface CandleChart {
  setBars(bars: Bar[], intraday: boolean, decimals: number): void;
  /** Updates the last bar, or adds one after it (from a live trade). */
  updateBar(bar: Bar): void;
  destroy(): void;
}

// Times stay real UTC timestamps; only their labels are written in a time zone.
// (Shifting the timestamps themselves breaks on the night daylight saving ends:
// 1:00 to 2:00 AM happens twice, two hourly candles land on the same time, and
// the chart refuses the data.)
//
// Intraday bars are labelled in your time zone. Daily and weekly bars are
// labelled by their UTC date: Coinbase days start at 00:00 UTC and Schwab's at
// midnight Central (05:00 or 06:00 UTC), so the UTC date is right for both.
function labels(intraday: boolean) {
  const timeZone = intraday ? undefined : "UTC";
  const format = (options: Intl.DateTimeFormatOptions) => new Intl.DateTimeFormat(undefined, { ...options, timeZone });
  const year = format({ year: "numeric" });
  const month = format({ month: "short" });
  const day = format({ day: "numeric" });
  const clock = format({ hour: "numeric", minute: "2-digit" });
  const crosshair = intraday
    ? format({ weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })
    : format({ weekday: "short", year: "numeric", month: "short", day: "numeric" });
  const date = (time: Time) => new Date((time as number) * 1000);

  return {
    tick(time: Time, type: TickMarkType): string {
      switch (type) {
        case TickMarkType.Year:
          return year.format(date(time));
        case TickMarkType.Month:
          return month.format(date(time));
        case TickMarkType.DayOfMonth:
          return day.format(date(time));
        default:
          return clock.format(date(time));
      }
    },
    crosshair: (time: Time) => crosshair.format(date(time)),
  };
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
    // Free-moving crosshair (Magnet, the default, snaps to closes), with tags on both axes
    crosshair: {
      mode: CrosshairMode.Normal,
      vertLine: { color: THEME.crosshair, labelBackgroundColor: THEME.label },
      horzLine: { color: THEME.crosshair, labelBackgroundColor: THEME.label },
    },
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
    setBars(bars, intraday, decimals) {
      byTime = new Map(bars.map((b) => [b.time, b]));
      const label = labels(intraday);
      chart.applyOptions({
        timeScale: { timeVisible: intraday, tickMarkFormatter: label.tick },
        localization: { timeFormatter: label.crosshair },
      });
      candles.applyOptions({ priceFormat: { type: "price", precision: decimals, minMove: 10 ** -decimals } });
      candles.setData(bars.map(candlePoint));
      volume.setData(bars.map(volumePoint));
      const n = bars.length;
      chart.timeScale().setVisibleLogicalRange({ from: Math.max(0, n - BARS_IN_VIEW), to: n + 3 });
    },
    updateBar(bar) {
      byTime.set(bar.time, bar);
      candles.update(candlePoint(bar));
      volume.update(volumePoint(bar));
    },
    destroy() {
      chart.unsubscribeCrosshairMove(hover);
      chart.remove();
    },
  };
}
