import type { Position } from "../../account/types";
import { shares } from "../../format";
import { money, percentOf, signedMoney, signedPercent, tone } from "../../money";
import { Link } from "../../router";

/** Symbol, shares, price, value, today, total return. Symbols open in Charts. */
export function PositionsTable({ positions }: { positions: Position[] }) {
  if (positions.length === 0) return <p className="quiet">No positions in this account.</p>;
  return (
    <div className="table-scroll">
      <table className="positions">
        <thead>
          <tr>
            <th scope="col">Symbol</th>
            <th scope="col">Shares</th>
            <th scope="col">Price</th>
            <th scope="col">Value</th>
            <th scope="col">Today</th>
            <th scope="col">Total return</th>
          </tr>
        </thead>
        <tbody>
          {positions.map((p) => {
            const today = percentOf(p.day_change_cents, p.market_value_cents - p.day_change_cents);
            const total = percentOf(p.open_pnl_cents, p.market_value_cents - p.open_pnl_cents);
            return (
              <tr key={p.symbol}>
                <th scope="row">
                  <Link to={`/charts?symbol=${encodeURIComponent(p.symbol)}`} className="num">
                    {p.symbol}
                  </Link>
                  {p.description && <div className="quiet position-name">{p.description}</div>}
                </th>
                <td className="num">{shares(p.quantity)}</td>
                <td className="num">{money(p.price_cents)}</td>
                <td className="num">{money(p.market_value_cents)}</td>
                <td className={`num ${tone(today)}`}>{signedPercent(today)}</td>
                <td className={`num ${tone(p.open_pnl_cents)}`}>
                  {signedMoney(p.open_pnl_cents)} <span className="quiet">({signedPercent(total)})</span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
