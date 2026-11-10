import { useEffect, useRef, useState } from "react";
import { summarize } from "./connection";
import { SettingsPanel } from "./SettingsPanel";
import { useServerStatus } from "./useServerStatus";

const PANEL_ID = "settings-panel";

/** The status dot on the right of the top bar. Clicking it opens the settings panel. */
export function ConnectionStatus() {
  const state = useServerStatus();
  const { label, tone } = summarize(state);
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);

  // Close on Escape or on a click anywhere outside
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && setOpen(false);
    const onClick = (event: MouseEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onClick);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onClick);
    };
  }, [open]);

  return (
    <div className="connection" ref={root}>
      <button
        type="button"
        className="connection-button"
        aria-expanded={open}
        aria-controls={PANEL_ID}
        onClick={() => setOpen(!open)}
      >
        <span className={`dot ${tone}`} aria-hidden="true" />
        {label}
      </button>
      {open && <SettingsPanel id={PANEL_ID} state={state} />}
    </div>
  );
}
