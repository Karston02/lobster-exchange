import { useEffect, useState, type FormEvent, type RefObject } from "react";
import { TIMEFRAMES, type Timeframe } from "./bars";
import { FullScreenButton } from "./FullScreenButton";

interface Props {
  fullScreenTarget: RefObject<HTMLElement | null>;
  symbol: string;
  timeframe: Timeframe;
  onSymbol: (symbol: string) => void;
  onTimeframe: (timeframe: Timeframe) => void;
}

const TIMEFRAME_NAMES: Record<Timeframe, string> = {
  "1m": "1 minute",
  "5m": "5 minutes",
  "15m": "15 minutes",
  "1h": "1 hour",
  "4h": "4 hours",
  D: "1 day",
  W: "1 week",
};

/** The top toolbar: symbol box, timeframe buttons, and full screen on the right. */
export function Toolbar({ fullScreenTarget, symbol, timeframe, onSymbol, onTimeframe }: Props) {
  const [typed, setTyped] = useState(symbol);
  useEffect(() => setTyped(symbol), [symbol]);

  function submit(event: FormEvent) {
    event.preventDefault();
    const clean = typed.trim().toUpperCase();
    if (clean) onSymbol(clean);
  }

  return (
    <div className="chart-toolbar">
      <form onSubmit={submit} role="search">
        <label className="visually-hidden" htmlFor="chart-symbol">
          Symbol
        </label>
        <input
          id="chart-symbol"
          className="symbol-input num"
          value={typed}
          onChange={(e) => setTyped(e.target.value.toUpperCase())}
          onFocus={(e) => e.target.select()}
          spellCheck={false}
          autoComplete="off"
          maxLength={12}
        />
      </form>
      <div role="group" aria-label="Timeframe" className="timeframes">
        {TIMEFRAMES.map((tf) => (
          <button
            key={tf}
            type="button"
            aria-pressed={tf === timeframe}
            aria-label={TIMEFRAME_NAMES[tf]}
            title={TIMEFRAME_NAMES[tf]}
            onClick={() => onTimeframe(tf)}
          >
            {tf}
          </button>
        ))}
      </div>
      <FullScreenButton target={fullScreenTarget} />
    </div>
  );
}
