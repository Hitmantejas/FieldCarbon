import { useEffect, useRef, type CSSProperties, type ReactNode } from "react";
import type { FarmId } from "../api";
import { ThemeToggle } from "./ThemeToggle";

export type StopId = "farm" | "pain" | "plan" | "sharpen" | "report";

// Stops follow the farmer's path (CLAUDE.md section 7). Only built stops are live; the rest are struck.
export const STOPS: { id: StopId; name: string; built: boolean }[] = [
  { id: "farm", name: "Your farm", built: true },
  { id: "pain", name: "Pain points", built: true },
  { id: "plan", name: "Plan", built: true },
  { id: "sharpen", name: "Sharpen", built: true },
  { id: "report", name: "Report", built: true },
];

// Same real farm, two data tiers (CLAUDE.md section 5, Demo).
export const FARMS: { id: FarmId; name: string; tier: string }[] = [
  { id: "a", name: "Farm A", tier: "Telemetry" },
  { id: "b", name: "Farm B", tier: "Receipts" },
];

const step = (i: number) => ({ "--i": i }) as CSSProperties;

interface Props {
  current: StopId;
  onGo: (id: StopId) => void;
  farm: FarmId;
  onFarm: (id: FarmId) => void;
  attribution?: string;
  children: ReactNode;
}

export function Docket({ current, onGo, farm, onFarm, attribution, children }: Props) {
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
      <div className="no-print mx-auto flex max-w-[36rem] justify-end pb-3">
        <ThemeToggle />
      </div>
      <main className="torn mx-auto max-w-[36rem] bg-paper text-ink shadow-[0_6px_18px_-8px_rgb(0_0_0/0.45)]">
        <p
          className="print border-b-2 border-dashed border-rule bg-mark px-4 py-2 font-mono text-xs uppercase tracking-widest text-on-mark"
          style={step(0)}
        >
          Demo data: illustrative
        </p>
        <header className="print flex flex-wrap items-end justify-between gap-3 px-4 pb-1 pt-5" style={step(1)}>
          <h1 className="font-display text-4xl font-extrabold uppercase leading-none tracking-wide">FieldCarbon</h1>
          <div role="group" aria-label="Which view of the farm" className="flex gap-1 font-mono text-xs uppercase tracking-widest">
            {FARMS.map((f) => (
              <button
                key={f.id}
                onClick={() => onFarm(f.id)}
                aria-pressed={farm === f.id}
                className={`btn-tab min-h-11 border-2 px-2 text-left leading-tight uppercase ${farm === f.id ? "border-ink bg-ink font-bold text-paper" : "border-rule text-ink-soft hover:border-ink"}`}
              >
                {f.name}
                <span className="block text-[0.65rem] font-normal">{f.tier}</span>
              </button>
            ))}
          </div>
        </header>
        <nav aria-label="Steps" className="print no-print overflow-x-auto px-4 pb-4 pt-2" style={step(2)}>
          <ol className="flex min-w-max items-end gap-5 border-b-2 border-ink font-mono text-xs uppercase tracking-widest">
            {STOPS.map((s) => (
              <li key={s.id}>
                {s.built ? (
                  <button
                    onClick={() => onGo(s.id)}
                    aria-current={s.id === current ? "step" : undefined}
                    className={`btn-tab inline-flex min-h-11 items-end border-b-4 pb-2 uppercase ${s.id === current ? "border-ink font-bold" : "border-transparent text-ink-soft hover:border-rule"}`}
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
