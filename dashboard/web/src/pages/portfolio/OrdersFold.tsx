import type { Order } from "../../account/types";
import { Fold } from "../../components/Fold";
import { dateTime, shares, words } from "../../format";
import { money } from "../../money";

/** "Orders · 1 working": open orders first, then the last day's finished ones. */
export function OrdersFold({ orders }: { orders: Order[] | null }) {
  if (orders === null) return <Fold summary="Orders · loading…">{null}</Fold>;
  const open = orders.filter((o) => o.is_open);
  const summary = `Orders · ${open.length === 0 ? "none working" : `${open.length} working`}`;
  const sorted = [...open, ...orders.filter((o) => !o.is_open)];
  return (
    <Fold summary={summary}>
      {sorted.length === 0 ? (
        <p className="quiet">No open orders, and none in the last day.</p>
      ) : (
        <div className="table-scroll">
          <table className="orders">
            <thead>
              <tr>
                <th scope="col">Symbol</th>
                <th scope="col">Side</th>
                <th scope="col">Filled</th>
                <th scope="col">Type</th>
                <th scope="col">Price</th>
                <th scope="col">Status</th>
                <th scope="col">Entered</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((o) => (
                <tr key={o.order_id} className={o.is_open ? "" : "quiet"}>
                  <th scope="row" className="num">
                    {o.symbol}
                  </th>
                  <td>{words(o.side)}</td>
                  <td className="num">
                    {shares(o.filled_quantity)} / {shares(o.quantity)}
                  </td>
                  <td>{words(o.order_type)}</td>
                  <td className="num">{o.price_cents == null ? "—" : money(o.price_cents)}</td>
                  <td>{words(o.status)}</td>
                  <td>{dateTime(o.entered_time)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Fold>
  );
}
