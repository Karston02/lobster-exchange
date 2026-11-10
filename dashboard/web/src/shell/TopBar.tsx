import { Link } from "../router";
import { ROUTES } from "../routes";
import { ConnectionStatus } from "./ConnectionStatus";
import "./shell.css";

interface Props {
  path: string;
}

/** The bar on every page: logo, the six pages, and the connection status. */
export function TopBar({ path }: Props) {
  return (
    <header className="topbar">
      <Link to="/" className="logo">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="2" aria-hidden="true">
          <path d="M4 18 L9 12 L13 15 L20 6" />
          <path d="M15 6 H20 V11" />
        </svg>
        lobster
      </Link>
      <nav className="nav" aria-label="Main">
        {ROUTES.map((route) => (
          <Link key={route.path} to={route.path} aria-current={route.path === path ? "page" : undefined}>
            {route.label}
          </Link>
        ))}
      </nav>
      <ConnectionStatus />
    </header>
  );
}
