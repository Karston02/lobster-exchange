import type { FillMessage } from "./types";
import { btc, clock, dollars, usd } from "../units";

interface Props {
  fills: FillMessage[];
}

/** The bot's most recent fills, newest first. */
export function Fills({ fills }: Props) {
  const recent = fills.slice(-25).reverse();
  return (
    <section className="panel fills">
      <h2>Recent fills</h2>
      {recent.length === 0 ? (
        <p className="hint">No fills yet</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>time</th>
              <th>side</th>
              <th>price</th>
              <th>BTC</th>
              <th>type</th>
              <th>fee</th>
            </tr>
          </thead>
          <tbody>
            {recent.map((f, i) => (
              <tr key={`${f.t}-${i}`} className={f.side}>
                <td>{clock(f.t)}</td>
                <td>{f.side}</td>
                <td>{dollars(f.price)}</td>
                <td>{btc(f.quantity, 4)}</td>
                <td>{f.maker ? "maker" : "taker"}</td>
                <td>{usd(f.fee_usd)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
