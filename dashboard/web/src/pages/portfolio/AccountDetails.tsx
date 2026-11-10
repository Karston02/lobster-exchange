import type { Account } from "../../account/types";
import { Fold } from "../../components/Fold";
import { dateTime, words } from "../../format";
import { money } from "../../money";
import { timeLeft } from "../../shell/connection";

interface Props {
  account: Account;
  fetchedAt: string | null;
  loginExpiresAt: string | null;
}

/** "Account details": number, buying power, type, last update, login expiry. */
export function AccountDetails({ account, fetchedAt, loginExpiresAt }: Props) {
  return (
    <Fold summary="Account details">
      <dl className="details">
        <dt>Account number</dt>
        <dd className="num">{account.last4}</dd>
        <dt>Buying power</dt>
        <dd className="num">{account.buying_power_cents == null ? "—" : money(account.buying_power_cents)}</dd>
        <dt>Account type</dt>
        <dd>{words(account.type)}</dd>
        <dt>Last update</dt>
        <dd>{fetchedAt ? dateTime(fetchedAt) : "—"}</dd>
        <dt>Schwab login ends</dt>
        <dd>{loginExpiresAt ? `${dateTime(loginExpiresAt)} (in ${timeLeft(loginExpiresAt)})` : "—"}</dd>
      </dl>
    </Fold>
  );
}
