import { ReplayView } from "../replay/ReplayView";

/** For now, the original crypto order book replay. The full page arrives in step 3. */
export function Backtests() {
  return (
    <main className="page wide">
      <ReplayView />
    </main>
  );
}
