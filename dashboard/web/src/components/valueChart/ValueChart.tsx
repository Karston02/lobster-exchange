import { useEffect, useRef, useState } from "react";
import { dateTime } from "../../format";
import { money } from "../../money";
import { usePolling } from "../../usePolling";
import { createValueChart, type Hover, type ValueChart as Chart, type ValuePoint } from "./lightweightValue";
import { isIntradayRange, RANGES, type History, type Range } from "./types";
import "./valueChart.css";

interface Props {
  account: string; // "all" or an account's last four digits
  initialRange: Range;
  /** The value right now (cents), to carry the 1D line up to this moment between recordings. */
  liveValueCents?: number | null;
  label?: string; // what the line is, for screen readers
}

const REFRESH_MS = 60_000; // the server records once a minute

const dollars = (cents: number) => cents / 100;
const toPoints = (list: History["points"]): ValuePoint[] => list.map((p) => ({ time: p.time, value: dollars(p.value_cents) }));

/** The value over a range, with range buttons (1D to All) under it. */
export function ValueChart({ account, initialRange, liveValueCents = null, label = "Value over time" }: Props) {
  const [range, setRange] = useState<Range>(initialRange);
  const history = usePolling<History>(`/api/history?range=${range}&account=${encodeURIComponent(account)}`, REFRESH_MS);
  const box = useRef<HTMLDivElement>(null);
  const chart = useRef<Chart | null>(null);
  const [hover, setHover] = useState<Hover | null>(null);

  useEffect(() => {
    const made = createValueChart(box.current!, setHover);
    chart.current = made;
    return () => made.destroy();
  }, []);

  const data = history.data?.range === range ? history.data : null;

  useEffect(() => {
    if (!chart.current || !data) return;
    const points = toPoints(data.points);
    // On 1D, extend the line to "now" with the live value, if the session is still on
    const now = Math.floor(Date.now() / 1000);
    const last = points[points.length - 1];
    if (range === "1D" && liveValueCents != null && now <= data.end && (!last || now - last.time >= 30)) {
      points.push({ time: now, value: dollars(liveValueCents) });
    }
    chart.current.setData(points, toPoints(data.benchmark), data.base_cents === null ? null : dollars(data.base_cents), isIntradayRange(range));
  }, [data, range, liveValueCents]);

  const empty = data !== null && data.points.length === 0;
  return (
    <section className="value-chart" aria-label={label}>
      <div className="value-readout num quiet" aria-live="off">
        {hover && hover.value !== null ? (
          <>
            {dateTime(new Date(hover.time * 1000).toISOString())} · <span className="value-now">{money(Math.round(hover.value * 100))}</span>
            {hover.benchmark !== null && <> · SPY line {money(Math.round(hover.benchmark * 100))}</>}
          </>
        ) : (
          " "
        )}
      </div>
      <div className="value-canvas" ref={box} />
      {empty && (
        <p className="value-empty quiet">
          No values recorded for this range yet. The server records your portfolio every minute while it runs.
        </p>
      )}
      <div role="group" aria-label="Range" className="ranges">
        {RANGES.map((r) => (
          <button key={r} type="button" aria-pressed={r === range} onClick={() => setRange(r)}>
            {r}
          </button>
        ))}
      </div>
    </section>
  );
}
