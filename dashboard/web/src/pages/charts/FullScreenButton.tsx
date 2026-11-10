import { useEffect, useState, type RefObject } from "react";

/** Puts `target` (the chart page) in full screen, or takes it out. Esc also exits. */
export function FullScreenButton({ target }: { target: RefObject<HTMLElement | null> }) {
  const [full, setFull] = useState(false);

  useEffect(() => {
    const update = () => setFull(document.fullscreenElement !== null);
    document.addEventListener("fullscreenchange", update);
    return () => document.removeEventListener("fullscreenchange", update);
  }, []);

  function toggle() {
    if (document.fullscreenElement) document.exitFullscreen();
    else target.current?.requestFullscreen();
  }

  const label = full ? "Exit full screen" : "Full screen";
  return (
    <button type="button" className="icon-button full-screen" onClick={toggle} aria-label={label} title={label}>
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
        {full ? (
          <path d="M9 4v5H4M15 4v5h5M9 20v-5H4M15 20v-5h5" />
        ) : (
          <path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5" />
        )}
      </svg>
    </button>
  );
}
