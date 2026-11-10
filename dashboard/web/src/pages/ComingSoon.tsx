interface Props {
  /** What the page will show, and which build step brings it. */
  children: string;
}

/** A page that isn't built yet: one quiet line saying what's coming. */
export function ComingSoon({ children }: Props) {
  return (
    <main className="page narrow">
      <p className="quiet">{children}</p>
    </main>
  );
}
