import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/** If a page crashes, show what went wrong in its place instead of a blank app.
 *  (React has no hook for this yet, so it's one of the few class components.) */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("page crashed:", error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <main className="page narrow">
        <p>This page hit an error: {this.state.error.message}</p>
        <p className="quiet">The other pages still work. Reload this one to try again.</p>
      </main>
    );
  }
}
