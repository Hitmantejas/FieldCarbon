import { useEffect, useRef, useState } from "react";
import { fetchDiagnosis } from "../fleetApi";
import type { Cause, CauseStatus, Diagnosis, Finding } from "../fleetApi";
import { litres } from "../format";
import { AuditBadge } from "./AuditBadge";
import { Rich } from "./Rich";
import { Stamp } from "./Stamp";

// The result is a word in a bordered tag, so it never relies on colour.
const STATUS_FORM: Record<CauseStatus, string> = {
  supported: "bg-ink text-paper",
  cannot_test: "border-2 border-ink-soft text-ink-soft",
  not_supported: "border-2 border-ink text-ink",
};

// Litres with thousands separators, percentages whole, hours to one decimal, and counts in the singular for one ("1 month", not "1 months").
const COUNTS: Record<string, string> = { notes: "note", months: "month", days: "day" };
const shownValue = (v: number | null, unit: string) => {
  if (v === null) return "not available";
  if (unit === "L") return `${litres(v)} L`;
  if (unit === "%") return `${Math.round(v)}%`;
  if (unit === "h") return `${v.toLocaleString("en-GB", { maximumFractionDigits: 1 })} h`;
  return `${v.toLocaleString("en-GB")} ${v === 1 && COUNTS[unit] ? COUNTS[unit] : unit}`;
};

function CauseRow({ c }: { c: Cause }) {
  return (
    <li className="space-y-1 py-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className={`rounded-full px-2 py-1 font-mono text-xs font-bold uppercase tracking-widest ${STATUS_FORM[c.status]}`}>{c.status_text}</span>
        {c.tag && <span className="rounded-full border-2 border-dashed border-ink px-2 py-1 font-mono text-xs uppercase tracking-widest">{c.tag}</span>}
      </div>
      <p className="font-bold">{c.title}</p>
      <p className="max-w-[70ch] text-sm text-ink-soft">{c.description}</p>
      {c.evidence && (
        <p className="flex flex-wrap items-center gap-3 text-sm">
          <span className="font-mono text-xs uppercase tracking-widest text-ink-soft">Evidence:</span>
          <span className="num">{shownValue(c.evidence.value, c.evidence.unit)}</span>
          {c.evidence_measures && <span>{c.evidence_measures}</span>}
          <Stamp label={c.evidence.label} />
          {c.explains_pct !== null && <span className="num">explains {c.explains_pct}% of the finding</span>}
        </p>
      )}
      {c.evidence && (
        <div className="text-sm text-ink-soft">
          <Rich text={c.evidence.how} />
        </div>
      )}
      {c.why && <p className="max-w-[70ch] text-sm">{c.suggested_by === "gemini" ? "Gemini's idea: " : "Gemini's reading: "}{c.why}</p>}
      {c.would_settle && (
        <p className="max-w-[70ch] text-sm">
          <span className="font-bold">What would settle it: </span>
          {c.would_settle}
        </p>
      )}
    </li>
  );
}

// F5: possible causes of one finding, each tested against the data by code. Gemini can add reasons and a summary.
export function DiagnosisPanel({ finding, onClose }: { finding: Finding | null; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const running = useRef<AbortController | null>(null);
  const [data, setData] = useState<Diagnosis | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = async (id: string, narrate: boolean) => {
    running.current?.abort();
    const ac = new AbortController();
    running.current = ac;
    setError(null);
    setBusy(narrate ? "Gemini is explaining the tested causes... this can take up to a minute." : "Testing the possible causes...");
    try {
      setData(await fetchDiagnosis(id, narrate, ac.signal));
    } catch (e) {
      if (!ac.signal.aborted) setError(e instanceof Error ? e.message : "The diagnosis could not be loaded.");
    } finally {
      if (!ac.signal.aborted) setBusy(null);
    }
  };

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (finding && !d.open) d.showModal();
    if (!finding && d.open) d.close();
    setData(null);
    if (finding) void load(finding.id, false);
    return () => running.current?.abort();
  }, [finding]);

  return (
    <dialog
      ref={ref}
      className="sheet max-h-[85dvh] overflow-y-auto"
      onClose={onClose}
      onClick={(e) => e.target === ref.current && onClose()}
      aria-labelledby="diagnosis-title"
    >
      {finding && (
        <div className="space-y-4 p-5">
          <h2 id="diagnosis-title" className="font-display text-3xl font-semibold leading-tight">
            What could explain this?
          </h2>
          <p className="max-w-[70ch]">{finding.title}</p>
          {data && (
            <p className="flex flex-wrap items-center gap-3">
              <span className="num text-xl">{shownValue(data.finding_figure.value, data.finding_figure.unit)}</span>
              <Stamp label={data.finding_figure.label} />
            </p>
          )}
          <p className="rounded-2xl border-2 border-ink p-3 font-bold">{data?.disclaimer ?? "Gemini suggests; code tests; a person decides."}</p>

          <div role="status" aria-live="polite" className="font-mono text-xs uppercase tracking-widest text-ink-soft">
            {busy}
          </div>
          {error && (
            <p role="alert" className="max-w-[70ch] rounded-2xl border-2 border-clay p-3 font-bold">
              {error}
            </p>
          )}

          {data?.summary && (
            <div className="space-y-2">
              <h3 className="font-mono text-xs uppercase tracking-widest text-ink-soft">Summary</h3>
              <p className="max-w-[70ch]">{data.summary.text}</p>
              <AuditBadge narrative={data.summary} />
            </div>
          )}

          {data && (
            <div>
              <h3 className="font-mono text-xs uppercase tracking-widest text-ink-soft">Possible causes, tested against the data</h3>
              <ul className="divide-y divide-rule">
                {data.hypotheses.map((c) => (
                  <CauseRow key={c.id} c={c} />
                ))}
              </ul>
              <p className="mt-2 text-sm text-ink-soft">
                Results and their order come from code. "Supported by the data" means the data fits this cause; it does not prove it.
              </p>
            </div>
          )}

          {data && !data.summary && (
            <button
              onClick={() => void load(finding.id, true)}
              disabled={busy !== null}
              className="btn-outline min-h-11 w-full border-2 border-ink px-4 text-sm font-bold disabled:opacity-60"
            >
              Ask Gemini to explain these results
            </button>
          )}
          <button onClick={onClose} className="btn-solid min-h-11 w-full border-2 border-ink bg-ink px-4 text-sm font-bold text-paper">
            Close
          </button>
        </div>
      )}
    </dialog>
  );
}
