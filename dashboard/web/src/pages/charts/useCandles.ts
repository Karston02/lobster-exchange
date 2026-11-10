import { useEffect, useState } from "react";
import { ApiError, getJson } from "../../api";
import { toBar, type Bar, type CandlesResponse, type Timeframe } from "./bars";

export interface Candles {
  bars: Bar[];
  decimals: number; // how many decimal places prices have
  loading: boolean;
  error: ApiError | null;
}

/** Loads the candles for one symbol and timeframe (again whenever either changes). */
export function useCandles(symbol: string, timeframe: Timeframe): Candles {
  const [state, setState] = useState<Candles>({ bars: [], decimals: 2, loading: true, error: null });

  useEffect(() => {
    let cancelled = false;
    setState({ bars: [], decimals: 2, loading: true, error: null });
    const url = `/api/candles?symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}`;
    getJson<CandlesResponse>(url)
      .then(
        (data) =>
          !cancelled &&
          setState({
            bars: data.candles.map((c) => toBar(c, data.decimals)),
            decimals: data.decimals,
            loading: false,
            error: null,
          }),
      )
      .catch((error) => !cancelled && setState({ bars: [], decimals: 2, loading: false, error: error as ApiError }));
    return () => {
      cancelled = true;
    };
  }, [symbol, timeframe]);

  return state;
}
