import type { Account } from "../../account/types";
import { money, percentOf, signedMoney, signedPercent, tone } from "../../money";

/** The account's name, its total value, then Today, Open P&L and Cash. */
export function AccountSummary({ account }: { account: Account }) {
  const today = percentOf(account.day_change_cents, account.total_value_cents - account.day_change_cents);
  return (
    <section aria-label="Account summary">
      <div className="quiet">{account.name}</div>
      <div className="num portfolio-value">{money(account.total_value_cents)}</div>
      <dl className="portfolio-stats">
        <div>
          <dt>Today</dt>
          <dd className={`num ${tone(account.day_change_cents)}`}>
            {signedMoney(account.day_change_cents)} <span className="quiet">({signedPercent(today)})</span>
          </dd>
        </div>
        <div>
          <dt>Open P&amp;L</dt>
          <dd className={`num ${tone(account.open_pnl_cents)}`}>{signedMoney(account.open_pnl_cents)}</dd>
        </div>
        <div>
          <dt>Cash</dt>
          <dd className="num">{money(account.cash_cents)}</dd>
        </div>
      </dl>
    </section>
  );
}
