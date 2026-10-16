import { useEffect, useRef, type CSSProperties, type ReactNode } from "react";
import type { ScreenId } from "../route";
import { ThemeToggle } from "./ThemeToggle";

// Only built screens are links; the rest are struck through until they exist.
export const SCREENS: { id: ScreenId; name: string; built: boolean }[] = [
  { id: "overview", name: "Fleet overview", built: true },
  { id: "ask", name: "Ask the analyst", built: true },
  { id: "sites", name: "Sites & machines", built: true },
  { id: "jobs", name: "Jobs & fields", built: true },
  { id: "opportunities", name: "Opportunities", built: true },
  { id: "proof", name: "Proof", built: true },
  { id: "control", name: "Fuel control", built: true },
  { id: "whatif", name: "What if", built: true },
  { id: "clients", name: "Clients", built: true },
  { id: "reports", name: "Reports", built: true },
];

const step = (i: number) => ({ "--i": i }) as CSSProperties;

interface Props {
  current: ScreenId;
  onGo: (id: ScreenId) => void;
  attribution: string;
  children: ReactNode;
}

export function Shell({ current, onGo, attribution, children }: Props) {
  const screen = useRef<HTMLDivElement>(null);
  const first = useRef(true);

  // Moving between screens: start at the top and put keyboard / screen-reader focus on the new screen.
  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    window.scrollTo({ top: 0 });
    screen.current?.focus({ preventScroll: true });
  }, [current]);

  return (
    <div className="contours min-h-dvh bg-desk px-4 pb-16 pt-4 lg:px-8">
      <div className="mx-auto grid max-w-[84rem] gap-6 lg:grid-cols-[13rem_1fr]">
        <aside className="no-print lg:sticky lg:top-4 lg:self-start">
          <p className="font-display text-4xl font-bold leading-none tracking-tight">
            Field<span className="text-moss">Carbon</span>
          </p>
          <nav aria-label="Screens" className="mt-6">
            <ul className="flex flex-wrap gap-1 text-[0.95rem] lg:flex-col">
              {SCREENS.map((s) => (
                <li key={s.id}>
                  {s.built ? (
                    <button
                      onClick={() => onGo(s.id)}
                      aria-current={s.id === current ? "page" : undefined}
                      className={`btn-tab min-h-11 w-full border-2 px-4 text-left ${s.id === current ? "border-ink bg-ink font-bold text-paper" : "border-transparent hover:border-ink"}`}
                    >
                      {s.name}
                    </button>
                  ) : (
                    <span
                      aria-disabled="true"
                      className="flex min-h-11 items-center border-2 border-transparent px-4 text-ink-soft line-through decoration-2"
                    >
                      {s.name}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          </nav>
          <div className="mt-6">
            <ThemeToggle />
          </div>
        </aside>
        <main className="min-w-0 rounded-[1.75rem] bg-paper text-ink shadow-[0_1px_2px_oklch(0%_0_0/0.06),0_12px_32px_-12px_oklch(30%_0.04_150/0.3)]">
          <div
            className="rise flex flex-wrap items-center justify-between gap-2 px-6 pb-1 pt-5 font-mono text-xs uppercase tracking-widest text-ink-soft"
            style={step(0)}
          >
            <span>Company year · 1 May 2025 to 30 April 2026</span>
            <span className="rounded-full bg-mark px-3 py-1 font-bold text-on-mark">Demo data: illustrative</span>
          </div>
          <div ref={screen} key={current} tabIndex={-1} className="outline-none">
            {children}
          </div>
          <footer className="border-t border-rule px-6 py-5 text-sm text-ink-soft">
            <p className="max-w-[80ch]">{attribution}</p>
          </footer>
        </main>
      </div>
    </div>
  );
}
