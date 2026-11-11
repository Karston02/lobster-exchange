import { useEffect, useRef, useState } from "react";
import { navigate, useSearchParams } from "../../router";
import { isIntraday, TIMEFRAMES, type Timeframe } from "./bars";
import { CandleChart } from "./CandleChart";
import { DrawingTools } from "./drawing/DrawingTools";
import type { Tool } from "./drawing/types";
import { useDrawings } from "./drawing/useDrawings";
import { Toolbar } from "./Toolbar";
import { useCandles } from "./useCandles";
import "./charts.css";

const DEFAULT_SYMBOL = "SPY";
const DEFAULT_TIMEFRAME: Timeframe = "D";

/** Charts: look at any instrument and draw on it. Stocks come from Schwab, coin
 *  pairs with a dash (BTC-USD) from Coinbase; the server picks. The symbol and
 *  timeframe live in the URL (/charts?symbol=AAPL&tf=1h), so links and the back
 *  button work. Drawings belong to the symbol and show on every timeframe. */
export function Charts() {
  const params = useSearchParams();
  const symbol = (params.get("symbol") ?? DEFAULT_SYMBOL).toUpperCase();
  const tfParam = params.get("tf");
  const timeframe = TIMEFRAMES.find((tf) => tf === tfParam) ?? DEFAULT_TIMEFRAME;
  const { bars, decimals, loading, error } = useCandles(symbol, timeframe);
  const drawings = useDrawings(symbol);
  const [tool, setTool] = useState<Tool>("select");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const page = useRef<HTMLElement>(null);

  useEffect(() => setSelectedId(null), [symbol]);

  // Esc: back to the select tool, nothing selected. Delete or Backspace: delete the selection.
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if ((event.target as Element).closest("input, textarea")) return; // typing a symbol
      if (event.key === "Escape") {
        setTool("select");
        setSelectedId(null);
      } else if ((event.key === "Delete" || event.key === "Backspace") && selectedId) {
        drawings.remove(selectedId);
        setSelectedId(null);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selectedId, drawings]);

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
      <div className="chart-body">
        <DrawingTools
          tool={tool}
          onTool={setTool}
          canDelete={selectedId !== null}
          onDelete={() => {
            if (selectedId) drawings.remove(selectedId);
            setSelectedId(null);
          }}
        />
        <div className="chart-stage">
          <CandleChart
            symbol={symbol}
            timeframe={timeframe}
            bars={bars}
            intraday={isIntraday(timeframe)}
            decimals={decimals}
            drawing={{
              drawings: drawings.list,
              tool,
              selectedId,
              onSave: drawings.save,
              onSelect: setSelectedId,
              onToolDone: () => setTool("select"),
            }}
          />
          {loading && <p className="chart-note quiet">Loading {symbol}…</p>}
          {!loading && error && <p className="chart-note quiet">{error.message}</p>}
          {!loading && !error && bars.length === 0 && <p className="chart-note quiet">No candles for {symbol}.</p>}
        </div>
      </div>
    </main>
  );
}
