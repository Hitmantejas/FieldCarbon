import { useEffect, useRef, type CSSProperties, type ReactNode } from "react";
import { ThemeToggle } from "./ThemeToggle";

export type StopId = "farm" | "pain" | "goal" | "plan" | "sharpen" | "report";

// Stops follow the farmer's path (CLAUDE.md section 7). Only built stops are live; the rest are struck.
export const STOPS: { id: StopId; name: string; built: boolean }[] = [
  { id: "farm", name: "Your farm", built: true },
  { id: "pain", name: "Pain points", built: true },
  { id: "goal", name: "Goal", built: false },
  { id: "plan", name: "Plan", built: false },
  { id: "sharpen", name: "Sharpen", built: false },
  { id: "report", name: "Report", built: false },
];

const step = (i: number) => ({ "--i": i }) as CSSProperties;

interface Props {
  current: StopId;
  onGo: (id: StopId) => void;
  attribution?: string;
  children: ReactNode;
}

export function Docket({ current, onGo, attribution, children }: Props) {
  const screen = useRef<HTMLDivElement>(null);
  const first = useRef(true);

  // Moving between stops: start at the top and put keyboard / screen-reader focus on the new screen.
  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    window.scrollTo({ top: 0 });
    screen.current?.focus({ preventScroll: true });
  }, [current]);

  return (
    <div className="min-h-dvh bg-desk px-3 pb-16 pt-3 sm:px-6">
      <div className="mx-auto flex max-w-[36rem] justify-end pb-3">
        <ThemeToggle />
      </div>
      <main className="torn mx-auto max-w-[36rem] bg-paper text-ink shadow-[0_6px_18px_-8px_rgb(0_0_0/0.45)]">
        <p
          className="print border-b-2 border-dashed border-rule bg-mark px-4 py-2 font-mono text-xs uppercase tracking-widest text-on-mark"
          style={step(0)}
        >
          Demo data: illustrative
        </p>
        <header className="print flex items-baseline justify-between px-4 pb-1 pt-5" style={step(1)}>
          <h1 className="font-display text-4xl font-extrabold uppercase leading-none tracking-wide">FieldCarbon</h1>
          <span className="font-mono text-xs uppercase tracking-widest text-ink-soft">Farm A</span>
        </header>
        <nav aria-label="Steps" className="print overflow-x-auto px-4 pb-4 pt-2" style={step(2)}>
          <ol className="flex min-w-max items-end gap-5 border-b-2 border-ink font-mono text-xs uppercase tracking-widest">
            {STOPS.map((s) => (
              <li key={s.id}>
                {s.built ? (
                  <button
                    onClick={() => onGo(s.id)}
                    aria-current={s.id === current ? "step" : undefined}
                    className={`inline-flex min-h-11 items-end border-b-4 pb-2 uppercase ${s.id === current ? "border-ink font-bold" : "border-transparent text-ink-soft hover:border-rule"}`}
                  >
                    {s.name}
                  </button>
                ) : (
                  <span aria-disabled="true" className="inline-flex min-h-11 items-end border-b-4 border-transparent pb-2 text-ink-soft line-through decoration-2">
                    {s.name}
                  </span>
                )}
              </li>
            ))}
          </ol>
        </nav>
        <div ref={screen} key={current} tabIndex={-1} className="outline-none">
          {children}
        </div>
        <footer className="border-t-2 border-dashed border-rule px-4 py-5 text-sm text-ink-soft">
          <p className="max-w-[65ch]">{attribution ?? "Loading data source..."}</p>
        </footer>
      </main>
    </div>
  );
}
