import { useRef } from "react";
import { navigate, useSearchParams } from "../../router";
import { isIntraday, TIMEFRAMES, type Timeframe } from "./bars";
import { CandleChart } from "./CandleChart";
import { Toolbar } from "./Toolbar";
import { useCandles } from "./useCandles";
import "./charts.css";

const DEFAULT_SYMBOL = "SPY";
const DEFAULT_TIMEFRAME: Timeframe = "D";

/** Charts: look at any instrument. Stocks come from Schwab, coin pairs with a
 *  dash (BTC-USD) from Coinbase; the server picks. The symbol and timeframe live
 *  in the URL (/charts?symbol=AAPL&tf=1h), so links and the back button work. */
export function Charts() {
  const params = useSearchParams();
  const symbol = (params.get("symbol") ?? DEFAULT_SYMBOL).toUpperCase();
  const tfParam = params.get("tf");
  const timeframe = TIMEFRAMES.find((tf) => tf === tfParam) ?? DEFAULT_TIMEFRAME;
  const { bars, decimals, loading, error } = useCandles(symbol, timeframe);
  const page = useRef<HTMLElement>(null);

  const go = (s: string, tf: Timeframe) => navigate(`/charts?symbol=${encodeURIComponent(s)}&tf=${tf}`);

  return (
    <main className="charts-page" ref={page}>
      <Toolbar
        fullScreenTarget={page}
        symbol={symbol}
        timeframe={timeframe}
        onSymbol={(s) => go(s, timeframe)}
        onTimeframe={(tf) => go(symbol, tf)}
      />
      <div className="chart-stage">
        <CandleChart
          symbol={symbol}
          timeframe={timeframe}
          bars={bars}
          intraday={isIntraday(timeframe)}
          decimals={decimals}
        />
        {loading && <p className="chart-note quiet">Loading {symbol}…</p>}
        {!loading && error && <p className="chart-note quiet">{error.message}</p>}
        {!loading && !error && bars.length === 0 && <p className="chart-note quiet">No candles for {symbol}.</p>}
      </div>
    </main>
  );
}
