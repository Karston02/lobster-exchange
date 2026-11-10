import type { Hello, Tick } from "../types";
import { btc, clock, usd } from "../units";

interface Props {
  hello: Hello | null;
  tick: Tick | null;
}

/** The headline numbers: time, position, PnL, fees, fills. */
export function Stats({ hello, tick }: Props) {
  const cards: [string, string, string?][] = [
    ["Time", tick && hello ? `${clock(tick.t)} / ${clock(hello.duration_s)}` : "—"],
    ["Position", tick ? `${btc(tick.position)} BTC` : "—"],
    [
      "PnL",
      tick?.pnl_usd != null ? usd(tick.pnl_usd) : "—",
      tick?.pnl_usd != null ? (tick.pnl_usd >= 0 ? "up" : "down") : undefined,
    ],
    ["Fees", tick ? usd(tick.fees_usd) : "—"],
    ["Fills", tick ? String(tick.fill_count) : "—"],
    ["Rejected", tick ? String(tick.rejections) : "—"],
  ];
  return (
    <section className="stats">
      {cards.map(([label, value, tone]) => (
        <div key={label} className={`panel card ${tone ?? ""}`}>
          <div className="label">{label}</div>
          <div className="value">{value}</div>
        </div>
      ))}
    </section>
  );
}
