import { ErrorBoundary } from "./components/ErrorBoundary";
import { usePath } from "./router";
import { pageFor } from "./routes";
import { TopBar } from "./shell/TopBar";

/** The app shell: the top bar, then whichever page the URL names. */
export default function App() {
  const path = usePath();
  const Page = pageFor(path);
  return (
    <>
      <TopBar path={path} />
      {/* keyed by path: going to another page clears an error */}
      <ErrorBoundary key={path}>
        <Page />
      </ErrorBoundary>
    </>
  );
}
