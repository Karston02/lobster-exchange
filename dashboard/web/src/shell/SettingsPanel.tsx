import { dateTime } from "../format";
import { timeLeft } from "./connection";
import type { StatusState } from "./useServerStatus";

interface Props {
  id: string;
  state: StatusState;
}

/** Account connections, opened from the status in the top bar. */
export function SettingsPanel({ id, state }: Props) {
  const online = state.kind === "online";
  const schwab = online ? state.status.schwab : null;

  return (
    <div id={id} className="settings-panel" role="dialog" aria-label="Connections">
      <h2>Connections</h2>
      <dl>
        <dt>Lobster server</dt>
        <dd>{online ? "Running" : state.kind === "loading" ? "Checking…" : "Not reachable"}</dd>
        <dt>Schwab</dt>
        <dd>{schwab ? (schwab.connected ? "Connected" : "Not connected") : "—"}</dd>
        {schwab && schwab.accounts.length > 0 && (
          <>
            <dt>Accounts</dt>
            <dd>{schwab.accounts.join(", ")}</dd>
          </>
        )}
        {schwab?.login_expires_at && (
          <>
            <dt>Login ends</dt>
            <dd>
              {dateTime(schwab.login_expires_at)}
              {schwab.connected && <span className="quiet"> · {timeLeft(schwab.login_expires_at)}</span>}
            </dd>
          </>
        )}
      </dl>
      {state.kind === "offline" && (
        <p className="hint">
          Start it with <code>python dashboard/server/app.py</code>.
        </p>
      )}
      {schwab?.message && <p className="hint">{schwab.message}</p>}
    </div>
  );
}
