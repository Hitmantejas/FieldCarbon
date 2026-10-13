import type { Figure } from "../api";
import { litres } from "../format";
import type { Finding } from "../fleetApi";
import { Stamp } from "./Stamp";

// Each finding opens its working sheet. Severity is a word, so it never relies on colour.
export function FindingList({ findings, onOpen }: { findings: Finding[]; onOpen: (title: string, shown: string, f: Figure) => void }) {
  return (
    <ul className="divide-y-2 divide-dashed divide-rule border-y-2 border-ink">
      {findings.map((f) => {
        const shown = `${litres(f.litres.value ?? 0)} ${f.litres.unit}`;
        return (
          <li key={f.title}>
            <button
              onClick={() => onOpen(f.title, shown, f.litres)}
              className="btn-row grid w-[calc(100%+1rem)] grid-cols-[5rem_1fr_auto] items-center gap-4 py-3 text-left"
            >
              <span className="bg-mark px-2 py-1 text-center font-mono text-xs font-bold uppercase tracking-widest text-on-mark">{f.severity}</span>
              <span className="max-w-[75ch]">{f.title}</span>
              <span className="flex items-center gap-3">
                <span className="num text-sm">{shown}</span>
                <Stamp label={f.litres.label} />
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
