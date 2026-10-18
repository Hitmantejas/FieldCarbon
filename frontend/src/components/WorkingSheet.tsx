import { Fragment, useEffect, useRef } from "react";
import type { Evidence, Label } from "../api";
import { linkText, useSources } from "../sources";
import { Rich } from "./Rich";
import { Stamp } from "./Stamp";

export interface Opened {
  title: string;
  shown: string;
  facts?: [string, string][]; // shown as a small table instead of one line
  label: Label;
  how: string;
  sourceIds?: string[];
  evidence?: Evidence[]; // the research rows behind an intervention
}

const STATUS_TEXT: Record<string, string> = {
  checked_derived: "We worked this figure out from numbers in the source; it does not state it itself",
  not_confirmed: "We could not find this figure in the source, so we show it but do not use it",
};

const UNIT_TEXT: Record<string, string> = {
  pct_of_tillage_fuel: "% of the fuel used for soil preparation",
  pct_of_tillage_and_seeding_fuel: "% of the fuel used for soil preparation and sowing",
  pct_of_field_fuel: "% of the fuel used in the field",
  pct_of_operation_fuel: "% of the fuel used for that job",
  pct_more_litres: "% more litres burned",
  pct_of_machine_ghg: "% of the machine's emissions",
  l_per_ha: "litres saved per hectare",
};
const words = (u: string) => UNIT_TEXT[u] ?? u.replace(/_/g, " ");

function SourceList({ ids }: { ids: string[] }) {
  const sources = useSources();
  return (
    <ul className="mt-2 space-y-3">
      {ids.map((id) => {
        const s = sources[id];
        return (
          <li key={id} className="text-sm">
            <span className="font-bold">{s?.title ?? id}</span>
            <span className="block text-ink-soft">
              {[s?.publisher_or_authors, s?.year].filter(Boolean).join(", ")}
              {s ? ` · ${linkText(s.link_status)}` : ""}
            </span>
            {s?.url && (
              <a href={s.url} target="_blank" rel="noreferrer" className="btn-link break-all underline underline-offset-4">
                {s.url}
              </a>
            )}
          </li>
        );
      })}
    </ul>
  );
}

function EvidenceList({ rows }: { rows: Evidence[] }) {
  return (
    <ul className="mt-2 space-y-4">
      {rows.map((e) => (
        <li key={e.coef_id} className="text-sm">
          <span className="font-bold">{e.title}</span>
          <span className="block text-ink-soft">
            {[e.region, e.year].filter(Boolean).join(", ")} · {linkText(e.link_status)}
          </span>
          <span className="num block">
            {e.low === e.high ? e.low : `${e.low} to ${e.high}`}{words(e.unit).startsWith("%") ? "" : " "}{words(e.unit)}
          </span>
          <span className="block text-ink-soft">Compared with: {e.baseline}</span>
          {e.is_manufacturer && <span className="block font-bold">This is a claim by the maker, so we show it but do not use it in our figures.</span>}
          {STATUS_TEXT[e.value_status] && <span className="block text-ink-soft">{STATUS_TEXT[e.value_status]}.</span>}
          {e.url && (
            <a href={e.url} target="_blank" rel="noreferrer" className="btn-link break-all underline underline-offset-4">
              {e.url}
            </a>
          )}
        </li>
      ))}
    </ul>
  );
}

// Every figure can open its working: how it was calculated, how sure we are, and where it comes from.
export function WorkingSheet({ opened, onClose }: { opened: Opened | null; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (opened && !d.open) d.showModal();
    if (!opened && d.open) d.close();
  }, [opened]);

  return (
    <dialog
      ref={ref}
      className="sheet max-h-[85dvh] overflow-y-auto"
      onClose={onClose}
      onClick={(e) => e.target === ref.current && onClose()}
      aria-labelledby="working-title"
    >
      {opened && (
        <div className="space-y-4 p-5">
          <div className="flex items-start justify-between gap-4">
            <h2 id="working-title" className="font-display text-3xl font-semibold leading-tight">{opened.title}</h2>
            <Stamp label={opened.label} />
          </div>
          {opened.facts ? (
            <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-1">
              {opened.facts.map(([k, v]) => (
                <Fragment key={k}>
                  <dt className="font-bold">{k}</dt>
                  <dd className="num">{v}</dd>
                </Fragment>
              ))}
            </dl>
          ) : (
            <p className="num text-xl">{opened.shown}</p>
          )}
          <div>
            <h3 className="font-mono text-xs uppercase tracking-widest text-ink-soft">How this was worked out</h3>
            <Rich text={opened.how} />
          </div>
          {opened.evidence && opened.evidence.length > 0 && (
            <div>
              <h3 className="font-mono text-xs uppercase tracking-widest text-ink-soft">What the research found</h3>
              <EvidenceList rows={opened.evidence} />
            </div>
          )}
          {opened.sourceIds && opened.sourceIds.length > 0 && (
            <div>
              <h3 className="font-mono text-xs uppercase tracking-widest text-ink-soft">Sources</h3>
              <SourceList ids={opened.sourceIds} />
            </div>
          )}
          <button onClick={onClose} className="btn-solid min-h-11 w-full border-2 border-ink bg-ink px-4 text-sm font-bold text-paper">
            Close
          </button>
        </div>
      )}
    </dialog>
  );
}
