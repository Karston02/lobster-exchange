// The app's pages, in the order the top bar shows them.

import type { ComponentType } from "react";
import { Backtests } from "./pages/Backtests";
import { Charts, ForwardTests, Home, Ideas, NotFound, Portfolio } from "./pages/placeholders";

export interface Route {
  path: string;
  label: string;
  Page: ComponentType;
}

export const ROUTES: Route[] = [
  { path: "/", label: "Home", Page: Home },
  { path: "/portfolio", label: "Portfolio", Page: Portfolio },
  { path: "/charts", label: "Charts", Page: Charts },
  { path: "/ideas", label: "Ideas", Page: Ideas },
  { path: "/backtests", label: "Backtests", Page: Backtests },
  { path: "/forward-tests", label: "Forward tests", Page: ForwardTests },
];

/** The page for a path; a trailing slash is ignored. */
export function pageFor(path: string): ComponentType {
  const clean = path.length > 1 ? path.replace(/\/+$/, "") : path;
  return ROUTES.find((route) => route.path === clean)?.Page ?? NotFound;
}
