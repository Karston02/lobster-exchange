import { useEffect, useState, type FormEvent, type RefObject } from "react";
import { TIMEFRAMES, type Timeframe } from "./bars";
import { Icons } from "./drawing/icons";
import { FullScreenButton } from "./FullScreenButton";

interface Props {
  fullScreenTarget: RefObject<HTMLElement | null>;
  symbol: string;
  timeframe: Timeframe;
  onSymbol: (symbol: string) => void;
  onTimeframe: (timeframe: Timeframe) => void;
  onUndo: () => void;
  onRedo: () => void;
  canUndo: boolean;
  canRedo: boolean;
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

/** The top toolbar: symbol box, timeframe buttons, and on the right undo, redo and full screen. */
export function Toolbar(props: Props) {
  const { fullScreenTarget, symbol, timeframe, onSymbol, onTimeframe } = props;
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
      <div className="toolbar-end">
        <button type="button" className="icon-button" aria-label="Undo (⌘Z)" title="Undo (⌘Z)" disabled={!props.canUndo} onClick={props.onUndo}>
          {Icons.undo}
        </button>
        <button type="button" className="icon-button" aria-label="Redo (⇧⌘Z)" title="Redo (⇧⌘Z)" disabled={!props.canRedo} onClick={props.onRedo}>
          {Icons.redo}
        </button>
        <FullScreenButton target={fullScreenTarget} />
      </div>
    </div>
  );
}
