import type { ReactNode } from "react";
import "./fold.css";

interface Props {
  /** Says what's inside, e.g. "Orders · 1 working", so it's useful even closed. */
  summary: ReactNode;
  children: ReactNode;
  open?: boolean;
}

/** A collapsed section: the design's way of keeping secondary things out of sight.
 *  Built on <details>, so keyboard and screen readers work without extra code. */
export function Fold({ summary, children, open = false }: Props) {
  return (
    <details className="fold" open={open}>
      <summary>{summary}</summary>
      <div className="fold-body">{children}</div>
    </details>
  );
}
