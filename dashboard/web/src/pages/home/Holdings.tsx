import type { Holding } from "../../account/types";
import { money, percentOf, signedPercent, tone } from "../../money";
import { Link } from "../../router";

interface Props {
  holdings: Holding[];
  cashCents: number;
}

/** One row per symbol: value and today's change. Rows open the symbol in Charts. */
export function Holdings({ holdings, cashCents }: Props) {
  return (
    <section aria-label="Holdings" className="home-rows">
      {holdings.map((h) => {
        const pct = percentOf(h.day_change_cents, h.market_value_cents - h.day_change_cents);
        return (
          <Link key={h.symbol} to={`/charts?symbol=${encodeURIComponent(h.symbol)}`} className="home-row">
            <span>
              <span className="num home-symbol">{h.symbol}</span>
              {h.description && <span className="quiet home-name">{h.description}</span>}
            </span>
            <span className="num">{money(h.market_value_cents)}</span>
            <span className={`num home-pct ${tone(pct)}`}>{signedPercent(pct)}</span>
          </Link>
        );
      })}
      <div className="home-row quiet">
        <span>Cash</span>
        <span className="num">{money(cashCents)}</span>
        <span />
      </div>
    </section>
  );
}
