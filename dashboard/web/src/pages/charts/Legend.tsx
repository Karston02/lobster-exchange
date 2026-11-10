import { signedPercent, tone } from "../../money";
import type { Bar } from "./bars";

const price = (dollars: number) => dollars.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const compact = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 2 });

/** Top-left of the chart: open, high, low, close and volume of the bar under the crosshair. */
export function Legend({ symbol, bar }: { symbol: string; bar: Bar }) {
  const change = bar.open ? ((bar.close - bar.open) / bar.open) * 100 : null;
  const cls = tone(change);
  return (
    <div className="legend num" aria-live="off">
      <span className="legend-symbol">{symbol}</span>
      <span>
        O <b className={cls}>{price(bar.open)}</b>
      </span>
      <span>
        H <b className={cls}>{price(bar.high)}</b>
      </span>
      <span>
        L <b className={cls}>{price(bar.low)}</b>
      </span>
      <span>
        C <b className={cls}>{price(bar.close)}</b>
      </span>
      <span className={cls}>{signedPercent(change)}</span>
      <span>
        V <b>{compact.format(bar.volume)}</b>
      </span>
    </div>
  );
}
