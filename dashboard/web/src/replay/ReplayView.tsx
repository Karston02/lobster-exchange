import { btc, dollars, usd } from "../units";
import { Controls } from "./Controls";
import { Fills } from "./Fills";
import { LineChart } from "./LineChart";
import { OrderBook } from "./OrderBook";
import { Stats } from "./Stats";
import { useReplay } from "./useReplay";
import "./replay.css";

/** The order book replay: a recorded crypto session with a strategy trading in it. */
export function ReplayView() {
  const replay = useReplay();
  const { history, fills } = replay;

  // Fills drawn on the price chart: green buys, red sells
  const markers = fills.map((f) => ({
    x: f.t,
    y: f.price,
    color: f.side === "buy" ? "#4FD1A1" : "#FF8F6B",
  }));

  return (
    <div className="replay">
      <header>
        <h1>Order book replay</h1>
        <span className={`status ${replay.status}`}>{replay.status}</span>
        {replay.hello && (
          <span className="subtitle">
            {replay.hello.strategy} on {replay.hello.recording}
          </span>
        )}
      </header>

      <Controls
        status={replay.status}
        onStart={replay.start}
        onStop={replay.stop}
        onPause={replay.pause}
        onResume={replay.resume}
        onSpeed={replay.setSpeed}
      />
      {replay.error && <p className="error">{replay.error}</p>}
      {replay.done && (
        <p className="done">
          Finished: PnL {replay.done.pnl_usd != null ? usd(replay.done.pnl_usd) : "—"}, fees{" "}
          {usd(replay.done.fees_usd)}, {replay.done.fill_count} fills, ending position{" "}
          {btc(replay.done.position)} BTC.
        </p>
      )}

      <Stats hello={replay.hello} tick={replay.tick} />

      <div className="grid">
        <OrderBook tick={replay.tick} />
        <div className="charts">
          <LineChart title="BTC mid" x={history.t} y={history.mid} format={dollars} markers={markers} />
          <LineChart
            title="Position (BTC)"
            x={history.t}
            y={history.position}
            format={(v) => btc(v, 4)}
            color="#ffb347"
            zeroLine
          />
          <LineChart title="PnL" x={history.t} y={history.pnl} format={usd} color="#ff7aa2" zeroLine />
        </div>
      </div>

      <Fills fills={fills} />
    </div>
  );
}
