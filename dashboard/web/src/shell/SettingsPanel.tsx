import type { StatusState } from "./useServerStatus";

interface Props {
  id: string;
  state: StatusState;
}

const yesNo = (value: boolean, yes: string, no: string) => (value ? yes : no);

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
        <dt>Schwab keys</dt>
        <dd>{schwab ? yesNo(schwab.credentials, "Set", "Missing") : "—"}</dd>
        <dt>Schwab login</dt>
        <dd>{schwab ? yesNo(schwab.token_saved, "Token saved", "Not logged in") : "—"}</dd>
      </dl>
      {state.kind === "offline" && (
        <p className="hint">
          Start it with <code>python dashboard/server/app.py</code>.
        </p>
      )}
      {schwab && !schwab.credentials && (
        <p className="hint">
          Copy <code>.env.example</code> to <code>.env</code> and add your Schwab keys.
        </p>
      )}
    </div>
  );
}
