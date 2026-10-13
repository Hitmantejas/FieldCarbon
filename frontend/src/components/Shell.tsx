import { useEffect, useRef, type CSSProperties, type ReactNode } from "react";
import type { ScreenId } from "../route";
import { ThemeToggle } from "./ThemeToggle";

// Only built screens are links; the rest are struck through until they exist.
export const SCREENS: { id: ScreenId; name: string; built: boolean }[] = [
  { id: "overview", name: "Fleet overview", built: true },
  { id: "sites", name: "Sites & machines", built: true },
  { id: "jobs", name: "Jobs & fields", built: true },
  { id: "opportunities", name: "Opportunities", built: true },
  { id: "control", name: "Fuel control", built: true },
  { id: "whatif", name: "What if", built: false },
  { id: "clients", name: "Clients", built: true },
  { id: "reports", name: "Reports", built: false },
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
    <div className="min-h-dvh bg-desk px-4 pb-16 pt-4 lg:px-8">
      <div className="mx-auto grid max-w-[84rem] gap-6 lg:grid-cols-[13rem_1fr]">
        <aside className="no-print lg:sticky lg:top-4 lg:self-start">
          <p className="font-display text-4xl font-extrabold uppercase leading-[0.9] tracking-wide">
            Field
            <br />
            Carbon
          </p>
          <nav aria-label="Screens" className="mt-6">
            <ul className="flex flex-wrap gap-1 font-mono text-xs uppercase tracking-widest lg:flex-col lg:gap-0">
              {SCREENS.map((s) => (
                <li key={s.id}>
                  {s.built ? (
                    <button
                      onClick={() => onGo(s.id)}
                      aria-current={s.id === current ? "page" : undefined}
                      className={`btn-tab min-h-11 w-full border-2 px-3 text-left uppercase ${s.id === current ? "border-ink bg-ink font-bold text-paper" : "border-transparent hover:border-ink"}`}
                    >
                      {s.name}
                    </button>
                  ) : (
                    <span
                      aria-disabled="true"
                      className="flex min-h-11 items-center border-2 border-transparent px-3 text-ink-soft line-through decoration-2"
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
        <main className="torn bg-paper text-ink shadow-[0_6px_18px_-8px_rgb(0_0_0/0.45)]">
          <div
            className="print flex flex-wrap items-center justify-between gap-2 border-b-2 border-dashed border-rule px-6 py-3 font-mono text-xs uppercase tracking-widest"
            style={step(0)}
          >
            <span>Company year · 1 May 2025 to 30 April 2026</span>
            <span className="bg-mark px-3 py-1 font-bold text-on-mark">Demo data: illustrative</span>
          </div>
          <div ref={screen} key={current} tabIndex={-1} className="outline-none">
            {children}
          </div>
          <footer className="border-t-2 border-dashed border-rule px-6 py-5 text-sm text-ink-soft">
            <p className="max-w-[80ch]">{attribution}</p>
          </footer>
        </main>
      </div>
    </div>
  );
}
