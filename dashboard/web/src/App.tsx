import { Controls } from "./components/Controls";
import { Fills } from "./components/Fills";
import { LineChart } from "./components/LineChart";
import { OrderBook } from "./components/OrderBook";
import { Stats } from "./components/Stats";
import { useReplay } from "./useReplay";
import { btc, dollars, usd } from "./units";

export default function App() {
  const replay = useReplay();
  const { history, fills } = replay;

  // Fills drawn on the price chart: green buys, red sells
  const markers = fills.map((f) => ({
    x: f.t,
    y: f.price,
    color: f.side === "buy" ? "#3ecf8e" : "#ff5c5c",
  }));

  return (
    <main>
      <header>
        <h1>lobster-exchange</h1>
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
    </main>
  );
}
