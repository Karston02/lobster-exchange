// Toolbar icons: small inline SVGs drawn with the current text color.

const ICON = { width: 18, height: 18, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.8 };

export const Icons = {
  select: (
    <svg {...ICON} aria-hidden="true">
      <path d="M5 3l14 8-6 2-2 6z" />
    </svg>
  ),
  trend: (
    <svg {...ICON} aria-hidden="true">
      <path d="M4 19L20 5" />
      <circle cx="4" cy="19" r="1.6" />
      <circle cx="20" cy="5" r="1.6" />
    </svg>
  ),
  ray: (
    <svg {...ICON} aria-hidden="true">
      <path d="M4 19L21 4" />
      <circle cx="4" cy="19" r="1.6" />
      <circle cx="12" cy="12" r="1.6" />
    </svg>
  ),
  hline: (
    <svg {...ICON} aria-hidden="true">
      <path d="M3 12h18" />
    </svg>
  ),
  rect: (
    <svg {...ICON} aria-hidden="true">
      <rect x="4" y="6" width="16" height="12" />
    </svg>
  ),
  channel: (
    <svg {...ICON} aria-hidden="true">
      <path d="M3 15L15 4M9 20L21 9" />
    </svg>
  ),
  fib: (
    <svg {...ICON} aria-hidden="true">
      <path d="M3 5h18M3 10h18M3 14h18M3 19h18" />
    </svg>
  ),
  text: (
    <svg {...ICON} aria-hidden="true">
      <path d="M5 6V4h14v2M12 4v16M9 20h6" />
    </svg>
  ),
  measure: (
    <svg {...ICON} aria-hidden="true">
      <path d="M12 3v18M8 7l4-4 4 4M8 17l4 4 4-4" />
    </svg>
  ),
  snap: (
    <svg {...ICON} aria-hidden="true">
      <path d="M6 4v8a6 6 0 0012 0V4M6 8h4M14 8h4" />
    </svg>
  ),
  lock: (
    <svg {...ICON} aria-hidden="true">
      <rect x="5" y="11" width="14" height="9" rx="1" />
      <path d="M8 11V8a4 4 0 018 0v3" />
    </svg>
  ),
  trash: (
    <svg {...ICON} aria-hidden="true">
      <path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3" />
    </svg>
  ),
  undo: (
    <svg {...ICON} aria-hidden="true">
      <path d="M9 14L4 9l5-5M4 9h11a5 5 0 010 10h-3" />
    </svg>
  ),
  redo: (
    <svg {...ICON} aria-hidden="true">
      <path d="M15 14l5-5-5-5M20 9H9a5 5 0 000 10h3" />
    </svg>
  ),
};
