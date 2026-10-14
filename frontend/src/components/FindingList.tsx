import type { Figure } from "../api";
import { litres } from "../format";
import type { Finding, Severity } from "../fleetApi";
import { Stamp } from "./Stamp";

const SEVERITY_FORM: Record<Severity, string> = {
  high: "bg-clay text-paper",
  medium: "border-2 border-clay text-clay",
  low: "border-2 border-ink-soft text-ink-soft",
};

// Severity is a word, so it never relies on colour.
export function SeverityTag({ severity }: { severity: Severity }) {
  return (
    <span className={`rounded-full px-2 py-1 text-center font-mono text-xs font-bold uppercase tracking-widest ${SEVERITY_FORM[severity]}`}>{severity}</span>
  );
}

// Each finding opens its working sheet.
export function FindingList({ findings, onOpen }: { findings: Finding[]; onOpen: (title: string, shown: string, f: Figure) => void }) {
  return (
    <ul className="divide-y divide-rule">
      {findings.map((f) => {
        const shown = `${litres(f.litres.value ?? 0)} ${f.litres.unit}`;
        return (
          <li key={f.title}>
            <button
              onClick={() => onOpen(f.title, shown, f.litres)}
              className="btn-row grid w-[calc(100%+1rem)] grid-cols-[5.5rem_1fr] items-center gap-x-4 gap-y-2 sm:grid-cols-[5.5rem_1fr_auto] py-3 text-left"
            >
              <SeverityTag severity={f.severity} />
              <span className="max-w-[75ch]">{f.title}</span>
              <span className="col-start-2 flex items-center gap-3 sm:col-start-auto">
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
