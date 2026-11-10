import { useState } from "react";
import type { Accounts, Orders } from "../../account/types";
import { useLive } from "../../live/useLive";
import type { ServerStatus } from "../../shell/useServerStatus";
import { usePolling } from "../../usePolling";
import { AccountDetails } from "./AccountDetails";
import { AccountPicker } from "./AccountPicker";
import { AccountSummary } from "./AccountSummary";
import { OrdersFold } from "./OrdersFold";
import { PositionsTable } from "./PositionsTable";
import "./portfolio.css";

const ACCOUNT_MS = 15_000; // fallback while the live connection is down
const ORDERS_MS = 15_000;
const STATUS_MS = 60_000;

/** Portfolio: what do I own, and what orders are open? */
export function Portfolio() {
  const live = useLive();
  const useLiveData = live.connected && live.message !== null;
  const polled = usePolling<Accounts>("/api/account", ACCOUNT_MS, !useLiveData);
  const orders = usePolling<Orders>("/api/orders", ORDERS_MS);
  const status = usePolling<ServerStatus>("/api/status", STATUS_MS);
  const [picked, setPicked] = useState<string | null>(null);

  const data: Accounts | null = useLiveData
    ? { accounts: live.message!.accounts, fetched_at: live.message!.as_of }
    : polled.data;

  if (!data && polled.loading) return <Message>Loading your accounts…</Message>;
  if (!data) return <Message>{polled.error?.message ?? "Couldn't load your accounts."}</Message>;

  const list = data.accounts;
  if (list.length === 0) return <Message>No accounts are linked to this Schwab login.</Message>;
  // Default to the biggest account; keep the picked one if it still exists
  const biggest = [...list].sort((a, b) => b.total_value_cents - a.total_value_cents)[0];
  const account = list.find((a) => a.last4 === picked) ?? biggest;
  const accountOrders = orders.data ? orders.data.orders.filter((o) => o.account_last4 === account.last4) : null;

  return (
    <main className="page narrow portfolio">
      <AccountPicker accounts={list} selected={account.last4} onSelect={setPicked} />
      <AccountSummary account={account} />
      <PositionsTable positions={account.positions} />
      <div>
        <OrdersFold orders={accountOrders} />
        <AccountDetails
          account={account}
          fetchedAt={data.fetched_at}
          loginExpiresAt={status.data?.schwab.login_expires_at ?? null}
        />
      </div>
      {!useLiveData && polled.error && <p className="quiet">Showing the last numbers: {polled.error.message}</p>}
    </main>
  );
}

function Message({ children }: { children: string }) {
  return (
    <main className="page narrow">
      <p className="quiet">{children}</p>
    </main>
  );
}
