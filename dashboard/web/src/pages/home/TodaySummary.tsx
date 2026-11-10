import type { Portfolio, Quote } from "../../account/types";
import { money, percentOf, signedMoney, signedPercent, tone } from "../../money";

interface Props {
  portfolio: Portfolio;
  spy: Quote | null;
}

/** The answer to "how is my portfolio doing today?": value, change, and SPY for comparison. */
export function TodaySummary({ portfolio, spy }: Props) {
  const changePct = percentOf(portfolio.day_change_cents, portfolio.previous_value_cents);
  return (
    <section aria-label="Portfolio today">
      <div className="quiet">Portfolio · today</div>
      <div className="num home-value">{money(portfolio.total_value_cents)}</div>
      <div className="num home-change">
        <span className={tone(portfolio.day_change_cents)}>
          {signedMoney(portfolio.day_change_cents)} ({signedPercent(changePct)}) today
        </span>
        {spy && (
          <span className="quiet home-benchmark">
            SPY <span className={tone(spy.change_pct)}>{signedPercent(spy.change_pct)}</span>
          </span>
        )}
      </div>
    </section>
  );
}
