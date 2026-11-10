import type { BotOrder, Tick } from "../types";
import { btc, dollars } from "../units";

interface Props {
  tick: Tick | null;
}

/**
 * A price ladder: asks above (lowest at the bottom), bids below (highest at
 * the top). Bars show size; rows where the bot has an order are highlighted,
 * with its size and how much is queued ahead of it.
 */
export function OrderBook({ tick }: Props) {
  if (!tick) return <section className="panel book empty">Waiting for data…</section>;

  const ordersAt = new Map<string, BotOrder>();
  for (const order of tick.orders) ordersAt.set(`${order.side}:${order.price}`, order);

  const largest = Math.max(1, ...tick.bids.map(([, q]) => q), ...tick.asks.map(([, q]) => q));
  const spread = tick.asks.length && tick.bids.length ? tick.asks[0][0] - tick.bids[0][0] : null;

  const row = (side: "buy" | "sell", price: number, quantity: number) => {
    const bot = ordersAt.get(`${side}:${price}`);
    return (
      <div key={`${side}${price}`} className={`row ${side} ${bot ? "mine" : ""}`}>
        <div className="bar" style={{ width: `${(quantity / largest) * 100}%` }} />
        <span className="price">{dollars(price)}</span>
        <span className="size">{btc(quantity)}</span>
        <span className="bot">
          {bot ? `bot ${btc(bot.quantity, 4)} · ${btc(bot.ahead ?? 0, 3)} ahead` : ""}
        </span>
      </div>
    );
  };

  // Bot orders away from the visible levels still deserve a mention
  const visible = new Set([
    ...tick.bids.map(([p]) => `buy:${p}`),
    ...tick.asks.map(([p]) => `sell:${p}`),
  ]);
  const hidden = tick.orders.filter((o) => !visible.has(`${o.side}:${o.price}`));

  return (
    <section className="panel book">
      <h2>Order book</h2>
      <div className="ladder">
        {[...tick.asks].reverse().map(([p, q]) => row("sell", p, q))}
        <div className="spread">
          spread {spread === null ? "—" : `${spread} tick${spread === 1 ? "" : "s"}`}
        </div>
        {tick.bids.map(([p, q]) => row("buy", p, q))}
      </div>
      {hidden.length > 0 && (
        <p className="hint">
          Off screen:{" "}
          {hidden.map((o) => `${o.side} ${btc(o.quantity, 4)} @ ${dollars(o.price)}`).join(", ")}
        </p>
      )}
    </section>
  );
}
