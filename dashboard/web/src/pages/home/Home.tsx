import type { Portfolio, Quotes } from "../../account/types";
import { useLive } from "../../live/useLive";
import { LoginButton, needsLogin } from "../../shell/LoginButton";
import { ValueChart } from "../../components/valueChart/ValueChart";
import { usePolling } from "../../usePolling";
import { Holdings } from "./Holdings";
import { TodaySummary } from "./TodaySummary";
import "./home.css";

// Polling is the fallback for when the live connection is down
const PORTFOLIO_MS = 15_000;
const QUOTES_MS = 30_000;

/** Home: how is my portfolio doing today? */
export function Home() {
  const live = useLive();
  const useLiveData = live.connected && live.message !== null;
  const portfolio = usePolling<Portfolio>("/api/portfolio", PORTFOLIO_MS, !useLiveData);
  const quotes = usePolling<Quotes>("/api/quotes?symbols=SPY", QUOTES_MS, !useLiveData);

  const data = useLiveData ? live.message!.portfolio : portfolio.data;
  const spy = (useLiveData ? live.message!.quotes.SPY : quotes.data?.quotes.SPY) ?? null;

  if (!data && portfolio.loading) return <Page>Loading your portfolio…</Page>;
  if (!data)
    return (
      <Page login={needsLogin(portfolio.error?.reason)}>{portfolio.error?.message ?? "Couldn't load your portfolio."}</Page>
    );

  return (
    <main className="page narrow home">
      <div>
        <TodaySummary portfolio={data} spy={spy} streaming={useLiveData && live.message!.streaming} />
        <ValueChart account="all" initialRange="1D" liveValueCents={data.total_value_cents} label="Portfolio value, with SPY for comparison" />
      </div>
      <Holdings holdings={data.holdings} cashCents={data.cash_cents} />
      {!useLiveData && portfolio.error && <p className="quiet">Showing the last numbers: {portfolio.error.message}</p>}
    </main>
  );
}

function Page({ children, login = false }: { children: string; login?: boolean }) {
  return (
    <main className="page narrow">
      <p className="quiet">{children}</p>
      {login && <LoginButton />}
    </main>
  );
}
