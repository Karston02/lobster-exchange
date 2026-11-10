import type { Portfolio, Quotes } from "../../account/types";
import { usePolling } from "../../usePolling";
import { Holdings } from "./Holdings";
import { TodaySummary } from "./TodaySummary";
import "./home.css";

const PORTFOLIO_MS = 15_000; // the server reuses Schwab answers for 10 s, so this costs little
const QUOTES_MS = 30_000;

/** Home: how is my portfolio doing today? */
export function Home() {
  const portfolio = usePolling<Portfolio>("/api/portfolio", PORTFOLIO_MS);
  const quotes = usePolling<Quotes>("/api/quotes?symbols=SPY", QUOTES_MS);

  if (portfolio.loading) return <Page>Loading your portfolio…</Page>;
  if (!portfolio.data) return <Page>{portfolio.error?.message ?? "Couldn't load your portfolio."}</Page>;

  const data = portfolio.data;
  return (
    <main className="page narrow home">
      <TodaySummary portfolio={data} spy={quotes.data?.quotes.SPY ?? null} />
      <Holdings holdings={data.holdings} cashCents={data.cash_cents} />
      {portfolio.error && <p className="quiet">Showing the last numbers: {portfolio.error.message}</p>}
    </main>
  );
}

function Page({ children }: { children: string }) {
  return (
    <main className="page narrow">
      <p className="quiet">{children}</p>
    </main>
  );
}
