// Every Lightweight Charts call for the value charts (Home, Portfolio) lives here,
// like pages/charts/lightweight.ts does for candles.

import {
  AreaSeries,
  ColorType,
  createChart,
  CrosshairMode,
  LineSeries,
  LineStyle,
  type AutoscaleInfo,
  type IPriceLine,
  type MouseEventParams,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";
import { timeLabels } from "../../chartLabels";

const THEME = {
  bg: "#0e1116",
  text: "#9aa4b2",
  gain: "#4fd1a1",
  loss: "#ff8f6b",
  gainFill: "rgba(79, 209, 161, 0.10)",
  lossFill: "rgba(255, 143, 107, 0.10)",
  benchmark: "#6b7585",
  base: "#3a4250",
  crosshair: "#6b7585",
  label: "#1b2330",
};

/** A point to draw: Unix seconds and dollars (display only). */
export interface ValuePoint {
  time: number;
  value: number;
}

export interface Hover {
  time: number;
  value: number | null;
  benchmark: number | null;
}

export interface ValueChart {
  setData(points: ValuePoint[], benchmark: ValuePoint[], base: number | null, intraday: boolean): void;
  destroy(): void;
}

const at = (p: ValuePoint) => ({ time: p.time as UTCTimestamp, value: p.value });

/** The latest point at or before `time` (points ascending), or null. The two lines'
 *  times don't always match (SPY candles vs recorded minutes), so the readout uses
 *  each line's most recent value rather than an exact match. */
export function valueAt(points: ValuePoint[], time: number): number | null {
  let lo = 0;
  let hi = points.length - 1;
  let found: number | null = null;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (points[mid].time <= time) {
      found = points[mid].value;
      lo = mid + 1;
    } else hi = mid - 1;
  }
  return found;
}

/** A calm line chart: the value as a shaded line (green above `base`, orange below),
 *  SPY as a thin grey line, and `base` (e.g. yesterday's close) as a dashed line.
 *  No axes or grid; it doesn't scroll or zoom. */
export function createValueChart(container: HTMLElement, onHover: (hover: Hover | null) => void): ValueChart {
  const chart = createChart(container, {
    autoSize: true,
    layout: { background: { type: ColorType.Solid, color: THEME.bg }, textColor: THEME.text, fontFamily: "Inter, system-ui, sans-serif" },
    grid: { vertLines: { visible: false }, horzLines: { visible: false } },
    rightPriceScale: { visible: false },
    leftPriceScale: { visible: false },
    timeScale: { borderVisible: false, secondsVisible: false, fixLeftEdge: true, fixRightEdge: true },
    handleScroll: false,
    handleScale: false,
    crosshair: {
      mode: CrosshairMode.Magnet,
      horzLine: { visible: false, labelVisible: false },
      vertLine: { color: THEME.crosshair, style: LineStyle.Dashed, labelBackgroundColor: THEME.label },
    },
  });

  const spy = chart.addSeries(LineSeries, {
    color: THEME.benchmark,
    lineWidth: 1,
    priceLineVisible: false,
    lastValueVisible: false,
    crosshairMarkerVisible: false,
  });
  const value = chart.addSeries(AreaSeries, {
    lineWidth: 2,
    priceLineVisible: false,
    lastValueVisible: false,
  });

  let base: number | null = null;
  let baseLine: IPriceLine | null = null;
  // Keep the dashed base line on screen even when every value is above or below it
  value.applyOptions({
    autoscaleInfoProvider: (original: () => AutoscaleInfo | null): AutoscaleInfo | null => {
      const info = original();
      if (!info?.priceRange || base === null) return info;
      return {
        ...info,
        priceRange: {
          minValue: Math.min(info.priceRange.minValue, base),
          maxValue: Math.max(info.priceRange.maxValue, base),
        },
      };
    },
  });

  let values: ValuePoint[] = [];
  let benchmarks: ValuePoint[] = [];
  const hover = (param: MouseEventParams<Time>) => {
    if (param.time === undefined) return onHover(null);
    const t = param.time as number;
    onHover({ time: t, value: valueAt(values, t), benchmark: valueAt(benchmarks, t) });
  };
  chart.subscribeCrosshairMove(hover);

  return {
    setData(points, benchmark, newBase, intraday) {
      base = newBase;
      values = points;
      benchmarks = benchmark;
      const last = points[points.length - 1]?.value;
      const up = last === undefined || base === null || last >= base;
      value.applyOptions({
        lineColor: up ? THEME.gain : THEME.loss,
        topColor: up ? THEME.gainFill : THEME.lossFill,
        bottomColor: "rgba(0, 0, 0, 0)",
      });
      value.setData(points.map(at));
      spy.setData(benchmark.map(at));
      if (baseLine) value.removePriceLine(baseLine);
      baseLine =
        base === null
          ? null
          : value.createPriceLine({ price: base, color: THEME.base, lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: false, title: "" });
      const label = timeLabels(intraday);
      chart.applyOptions({
        timeScale: { timeVisible: intraday, tickMarkFormatter: label.tick },
        localization: { timeFormatter: label.crosshair },
      });
      chart.timeScale().fitContent();
    },
    destroy() {
      chart.unsubscribeCrosshairMove(hover);
      chart.remove();
    },
  };
}
