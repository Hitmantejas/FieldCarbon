import { useEffect, useRef, useState } from "react";
import type { Figure } from "../api";
import { useApi } from "../api";
import { DiagnosisPanel } from "../components/DiagnosisPanel";
import { FindingList, SeverityTag } from "../components/FindingList";
import { SectionHead } from "../components/SectionHead";
import { Stamp } from "../components/Stamp";
import { WorkingSheet, type Opened } from "../components/WorkingSheet";
import { checkDeliveryNote, NOTE_MAX_BYTES, NOTE_TYPES } from "../fleetApi";
import type { Anomalies, DeliveryNotes, DepotMonth, Finding, NoteCheck, NoteFinding, NoteVerdict, ReadLine, Reconciliation, Severity } from "../fleetApi";
import { litres } from "../format";

const SEVERITY_ORDER: Record<Severity, number> = { high: 0, medium: 1, low: 2 };
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const monthName = (key: string) => `${MONTHS[Number(key.slice(5, 7)) - 1]} ${key.slice(0, 4)}`;
const signed = (n: number) => `${n > 0 ? "+" : ""}${litres(n)}`;

function Loading({ what }: { what: string }) {
  return <p className="font-mono text-sm uppercase tracking-widest text-ink-soft">Loading {what}...</p>;
}

// A delivery-note finding is in litres, in pounds (a price difference), or has nothing to quantify.
const amount = (f: Figure) => (f.unit === "GBP" ? `£${Math.abs(f.value ?? 0).toFixed(2)}` : `${litres(f.value ?? 0)} L`);

function NoteFindings({ findings, onOpen }: { findings: NoteFinding[]; onOpen: (title: string, shown: string, f: Figure) => void }) {
  return (
    <ul className="divide-y divide-rule">
      {findings.map((f) => {
        const row = (
          <>
            <SeverityTag severity={f.severity} />
            <span className="max-w-[75ch]">
              {f.title}
              {f.on_note !== undefined && f.in_log !== undefined && f.kind === "date_differs" && (
                <span className="block text-sm text-ink-soft">Note: {String(f.on_note)}. Log: {String(f.in_log)}.</span>
              )}
              {f.reasons && <span className="block text-sm text-ink-soft">{f.reasons.join(" ")}</span>}
            </span>
            {f.figure ? (
              <span className="col-start-2 flex items-center gap-3 sm:col-start-auto">
                <span className="num text-sm">{amount(f.figure)}</span>
                <Stamp label={f.figure.label} />
              </span>
            ) : (
              <span />
            )}
          </>
        );
        return (
          <li key={f.kind + f.doc_no}>
            {f.figure ? (
              <button onClick={() => onOpen(f.title, amount(f.figure!), f.figure!)} className="btn-row grid w-[calc(100%+1rem)] grid-cols-[5.5rem_1fr] items-center gap-x-4 gap-y-2 sm:grid-cols-[5.5rem_1fr_auto] py-3 text-left">
                {row}
              </button>
            ) : (
              <div className="grid grid-cols-[5.5rem_1fr] items-center gap-x-4 gap-y-2 sm:grid-cols-[5.5rem_1fr_auto] py-3">{row}</div>
            )}
          </li>
        );
      })}
    </ul>
  );
}

function HowButton({ onClick, label }: { onClick: () => void; label: string }) {
  return (
    <button onClick={onClick} className="btn-outline min-h-11 border-2 border-ink px-4 text-sm font-bold" aria-label={`How ${label} was worked out`}>
      How this was worked out
    </button>
  );
}

const SAMPLES = [
  { name: "matches", title: "A note that matches" },
  { name: "litres-differ", title: "Litres differ" },
  { name: "price-differs", title: "Price differs" },
  { name: "not-in-log", title: "Not in the log" },
];
const VERDICTS: Record<NoteVerdict, string> = {
  matches_log: "Matches the fuel log",
  needs_attention: "Differs from the fuel log: look into this",
  needs_review: "Could not be read with confidence: check it by hand",
  not_a_delivery_note: "This does not look like a fuel delivery note",
};
const price = (l: ReadLine) =>
  l.unit_price == null ? "unreadable" : l.unit_price_unit === "pence_per_litre" ? `${l.unit_price}p` : `£${l.unit_price}`;
const shownNumber = (v: number | null) => (v == null ? "unreadable" : String(v));

// F7: a person hands over one photo of a delivery note; Gemini reads it, code checks it. Nothing is saved.
function NoteUpload({ onOpen }: { onOpen: (title: string, shown: string, f: Figure) => void }) {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<NoteCheck | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [photo, setPhoto] = useState<{ url: string; what: string } | null>(null);
  const running = useRef<AbortController | null>(null);

  useEffect(() => () => running.current?.abort(), []);
  useEffect(() => () => { if (photo) URL.revokeObjectURL(photo.url); }, [photo]);

  const send = async (blob: Blob, what: string) => {
    setResult(null);
    setError(null);
    if (!NOTE_TYPES.includes(blob.type)) return setError("Only JPEG, PNG or WebP photos can be read. Take a photo of the note and send that.");
    if (blob.size > NOTE_MAX_BYTES) return setError("The photo is over 5 MB. Please send a smaller photo of the note.");
    running.current?.abort();
    const ac = new AbortController();
    running.current = ac;
    setPhoto({ url: URL.createObjectURL(blob), what });
    setBusy(true);
    try {
      setResult(await checkDeliveryNote(blob, ac.signal));
    } catch (e) {
      if (!ac.signal.aborted) setError(e instanceof Error ? e.message : "The note could not be checked.");
    } finally {
      if (!ac.signal.aborted) setBusy(false);
    }
  };

  const sample = async (name: string, title: string) => {
    try {
      const r = await fetch(`/demo-notes/${name}.jpg`);
      if (!r.ok) throw new Error();
      await send(new Blob([await r.blob()], { type: "image/jpeg" }), `Sample note: ${title}`);
    } catch {
      setError("The sample note could not be loaded. Reload the page and try again.");
    }
  };

  return (
    <div className="mt-6 rounded-3xl border-2 border-ink p-4 sm:p-6">
      <h3 className="font-display text-2xl font-semibold">Check a delivery note</h3>
      <p className="mt-2 max-w-[70ch] text-ink-soft">
        Send a photo of one delivery note. Gemini reads what is printed; the same fixed rules and code check it against the fuel log. Nothing is
        saved: the note is not added to the log.
      </p>
      <div className="mt-4 flex flex-wrap items-end gap-4">
        <label className="flex flex-col gap-2 text-sm font-bold">
          Photo of a note (JPEG, PNG or WebP, up to 5 MB)
          <input
            type="file"
            accept={NOTE_TYPES.join(",")}
            disabled={busy}
            onChange={(e) => {
              const f = e.target.files?.[0];
              e.target.value = ""; // the same photo can be sent again
              if (f) void send(f, "Your photo");
            }}
            className="min-h-11 max-w-full border-2 border-ink bg-paper p-2 font-normal file:mr-3 file:min-h-9 file:border-0 file:bg-ink file:px-3 file:font-bold file:text-paper disabled:opacity-60"
          />
        </label>
      </div>
      <div role="group" aria-label="Try a sample note" className="mt-4 flex flex-wrap items-center gap-2 text-sm">
        <span className="font-mono text-xs uppercase tracking-widest text-ink-soft">Or try a sample note:</span>
        {SAMPLES.map((s) => (
          <button key={s.name} onClick={() => void sample(s.name, s.title)} disabled={busy} className="btn-outline min-h-11 border-2 border-ink px-4 font-bold disabled:opacity-60">
            {s.title}
          </button>
        ))}
      </div>
      <p className="mt-2 text-sm text-ink-soft">The sample notes are synthetic demo documents, made for this check.</p>

      <div role="status" aria-live="polite" className="mt-4 font-mono text-xs uppercase tracking-widest text-ink-soft">
        {busy && "Reading the note... this can take up to a minute."}
      </div>
      {error && (
        <p role="alert" className="mt-3 max-w-[70ch] rounded-2xl border-2 border-clay p-3 font-bold">
          {error}
        </p>
      )}

      {(result || busy) && photo && (
        <div className="mt-4 grid gap-6 md:grid-cols-[minmax(0,16rem)_1fr]">
          <figure>
            <img src={photo.url} alt={`${photo.what}, as sent`} className="w-full rounded-2xl border border-rule" />
            <figcaption className="mt-1 text-sm text-ink-soft">{photo.what}</figcaption>
          </figure>
          {result && (
            <div>
              <p className="text-lg font-bold">
                <span className="font-mono text-xs uppercase tracking-widest text-ink-soft">Verdict: </span>
                {VERDICTS[result.verdict]}
              </p>
              {result.read.lines.length > 0 && (
                <div className="mt-3 overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <caption className="mb-1 text-left text-ink-soft">
                      As read by Gemini: note {result.read.doc_number ?? "number unreadable"}, {result.read.supplier ?? "supplier unreadable"},{" "}
                      {result.read.date ?? "date unreadable"}
                    </caption>
                    <thead>
                      <tr className="border-b-2 border-rule font-mono text-xs uppercase tracking-widest text-ink-soft">
                        <th scope="col" className="py-2 font-normal">Product</th>
                        <th scope="col" className="py-2 text-right font-normal">Litres</th>
                        <th scope="col" className="py-2 text-right font-normal">Price per litre</th>
                        <th scope="col" className="py-2 pl-4 font-normal">Counts as fuel</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.read.lines.map((l, i) => (
                        <tr key={i} className="border-b border-rule">
                          <th scope="row" className="py-2 pr-2 font-normal">{l.product ?? "unreadable"}</th>
                          <td className="num py-2 text-right">{shownNumber(l.litres)}</td>
                          <td className="num py-2 text-right">{price(l)}</td>
                          <td className="py-2 pl-4">{result.validated_lines[i]?.counts ? "Yes" : "No"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {result.findings.length > 0 && (
                <div className="mt-3">
                  <NoteFindings findings={result.findings} onOpen={onOpen} />
                </div>
              )}
              <p className="mt-3 text-sm text-ink-soft">
                {result.usage && `Gemini used ${result.usage.total_tokens.toLocaleString("en-GB")} tokens to read it. `}Source: {result.data_source}
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function FuelControl() {
  const recon = useApi<Reconciliation>("/api/fleet/reconciliation");
  const anomalies = useApi<Anomalies>("/api/fleet/anomalies");
  const notes = useApi<DeliveryNotes>("/api/fleet/delivery-notes");
  const [opened, setOpened] = useState<Opened | null>(null);
  const [diagnosing, setDiagnosing] = useState<Finding | null>(null);
  const [depot, setDepot] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);

  const open = (title: string, shown: string, f: Figure) =>
    setOpened({ title, shown, label: f.label, how: f.how, sourceIds: f.source_ids });
  const openChecked = (title: string, c: { label: Figure["label"]; how: string; source_ids: string[] }) =>
    setOpened({ title, shown: "", label: c.label, how: c.how, sourceIds: c.source_ids });

  const bySeverity = <T extends { severity: Severity }>(xs: T[]) => [...xs].sort((a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity]);
  const r = recon.data;
  const depots = r ? [...new Map(r.depots.rows.map((d) => [d.depot_id, d.depot])).entries()] : [];
  const depotId = depot ?? depots[0]?.[0];
  const depotRows: DepotMonth[] = r?.depots.rows.filter((d) => d.depot_id === depotId) ?? [];
  const tolerance = r?.settings.stock_tolerance_l ?? 100;
  const machineRows = (r?.machine_months.rows ?? []).filter((m) => showAll || m.flagged);

  return (
    <div className="space-y-10 pb-10">
      <section className="px-6 pt-6" aria-labelledby="h-control">
        <h1 id="h-control" className="rise font-display text-5xl font-semibold leading-[1.02] sm:text-6xl tracking-tight" style={{ "--i": 1 } as React.CSSProperties}>
          Fuel control
        </h1>
        <p className="mt-3 max-w-[70ch] text-ink-soft">
          Fuel handed out against fuel burned, each depot's books against its tank, and things in the machines' own data that look odd. Each one is
          a reason to investigate, not proof of a fault or a loss.
        </p>
      </section>

      <section className="px-6" aria-labelledby="h-recon">
        <SectionHead id="h-recon" title="Fuel that does not add up" tone="mark" aside={r && <HowButton onClick={() => openChecked("Fuel that does not add up", r.depots)} label="the depot check" />} />
        {!r ? <Loading what="reconciliation" /> : r.findings.length === 0 ? <p>Nothing found.</p> : <FindingList findings={bySeverity(r.findings)} onOpen={open} onDiagnose={setDiagnosing} />}
      </section>

      <section className="px-6" aria-labelledby="h-notes">
        <SectionHead id="h-notes" title="Delivery notes against the fuel log" tone="solid" />
        {!notes.data ? (
          <Loading what="delivery notes" />
        ) : (
          <>
            <p className="mb-3 max-w-[70ch]">
              Gemini reads each delivery note; fixed rules and code check it against the log.{" "}
              <span className="font-bold">
                {notes.data.notes_matching_log} of {notes.data.notes} notes match
              </span>{" "}
              the {notes.data.log_rows} rows in the fuel log.
            </p>
            <dl className="mb-4 grid max-w-xl grid-cols-2 gap-4">
              {([["On the notes", notes.data.litres_on_notes], ["In the fuel log", notes.data.litres_in_log]] as [string, Figure][]).map(([name, f]) => (
                <button key={name} onClick={() => open(`Litres ${name.toLowerCase()}`, amount(f), f)} className="rounded-3xl bg-tint p-4 text-left transition-colors hover:bg-mark/40">
                  <dt className="font-mono text-xs uppercase tracking-widest text-ink-soft">{name}</dt>
                  <dd className="mt-1 flex items-center gap-3">
                    <span className="num text-2xl font-bold">{amount(f)}</span>
                    <Stamp label={f.label} />
                  </dd>
                </button>
              ))}
            </dl>
            {notes.data.findings.length === 0 ? <p>Every note matches the fuel log.</p> : <NoteFindings findings={notes.data.findings} onOpen={open} />}
            <p className="mt-2 text-sm text-ink-soft">
              {notes.data.data_source.includes("pending")
                ? "Gemini has not read these notes yet, so the check uses the text printed on them. "
                : `Source: ${notes.data.data_source}. `}
              Demo documents, illustrative.
            </p>
          </>
        )}
        <NoteUpload onOpen={open} />
      </section>

      <section className="px-6" aria-labelledby="h-odd">
        <SectionHead id="h-odd" title="Odd in the machines' data" tone="dashed" />
        {!anomalies.data ? <Loading what="machine findings" /> : <FindingList findings={anomalies.data.findings} onOpen={open} onDiagnose={setDiagnosing} />}
      </section>

      <section className="px-6" aria-labelledby="h-depot">
        <SectionHead id="h-depot" title="Depot stock, month end" tone="solid" aside={r && <HowButton onClick={() => openChecked("Depot stock", r.depots)} label="depot stock" />} />
        {!r ? (
          <Loading what="depots" />
        ) : (
          <>
            <div role="group" aria-label="Which depot" className="mb-3 flex flex-wrap gap-2 text-sm">
              {depots.map(([id, name]) => (
                <button
                  key={id}
                  onClick={() => setDepot(id)}
                  aria-pressed={id === depotId}
                  className={`btn-tab min-h-11 border-2 px-4 ${id === depotId ? "border-ink bg-ink font-bold text-paper" : "border-rule hover:border-ink"}`}
                >
                  {name}
                </button>
              ))}
            </div>
            <div className="overflow-x-auto">
            <table className="w-full text-left">
              <caption className="sr-only">Book stock against measured stock at each month end</caption>
              <thead>
                <tr className="border-b-2 border-rule font-mono text-xs uppercase tracking-widest text-ink-soft">
                  <th scope="col" className="py-2 font-normal">Month end</th>
                  <th scope="col" className="py-2 text-right font-normal">Books say (L)</th>
                  <th scope="col" className="py-2 text-right font-normal">Tank holds (L)</th>
                  <th scope="col" className="py-2 text-right font-normal">Difference (L)</th>
                  <th scope="col" className="py-2 pl-4 font-normal">Check</th>
                </tr>
              </thead>
              <tbody>
                {depotRows.map((d) => {
                  const off = Math.abs(d.gap_l) >= tolerance;
                  return (
                    <tr key={d.month_end} className={`border-b border-rule ${off ? "bg-mark text-on-mark" : ""}`}>
                      <th scope="row" className="py-2 pr-2 font-normal">{monthName(d.month_end)}</th>
                      <td className="num py-2 text-right">{litres(d.book_l)}</td>
                      <td className="num py-2 text-right">{litres(d.measured_l)}</td>
                      <td className="num py-2 text-right font-bold">{signed(d.book_l - d.measured_l)}</td>
                      <td className="py-2 pl-4 font-mono text-xs uppercase tracking-widest">{off ? "Look into this" : "Fine"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            </div>
            <p className="mt-2 text-sm text-ink-soft">A difference of {litres(tolerance)} litres or more is marked. Books say = deliveries minus fuel handed out. A positive difference means the tank holds less than the books say.</p>
          </>
        )}
      </section>

      <section className="px-6" aria-labelledby="h-machines">
        <SectionHead
          id="h-machines"
          title="Fuel handed out, against burned"
          tone="dashed"
          aside={r && <HowButton onClick={() => openChecked("Handed out against burned", r.machine_months)} label="handed out against burned" />}
        />
        {!r ? (
          <Loading what="machines" />
        ) : (
          <>
            <div className="mb-3 flex flex-wrap items-center gap-3">
              <Stamp label={r.machine_months.label} />
              <button onClick={() => setShowAll((v) => !v)} aria-pressed={showAll} className="btn-outline min-h-11 border-2 border-ink px-4 text-sm font-bold">
                {showAll ? "Show only the ones to look at" : `Show all ${r.machine_months.rows.length} machine-months`}
              </button>
            </div>
            {machineRows.length === 0 ? (
              <p>No machine took more than {Math.round((r.settings.ratio_limit - 1) * 100)}% above what it burned.</p>
            ) : (
              <div className="overflow-x-auto">
              <table className="w-full text-left">
                <caption className="sr-only">Fuel handed to each machine against fuel it burned, by month</caption>
                <thead>
                  <tr className="border-b-2 border-rule font-mono text-xs uppercase tracking-widest text-ink-soft">
                    <th scope="col" className="py-2 font-normal">Machine</th>
                    <th scope="col" className="py-2 font-normal">Month</th>
                    <th scope="col" className="py-2 text-right font-normal">Handed out (L)</th>
                    <th scope="col" className="py-2 text-right font-normal">Burned (L)</th>
                    <th scope="col" className="py-2 text-right font-normal">Ratio</th>
                    <th scope="col" className="py-2 pl-4 font-normal">Check</th>
                  </tr>
                </thead>
                <tbody>
                  {machineRows.map((m) => (
                    <tr key={m.machine_id + m.month} className={`border-b border-rule ${m.flagged ? "bg-mark text-on-mark" : ""}`}>
                      <th scope="row" className="py-2 pr-2 font-bold">{m.machine}</th>
                      <td className="py-2">{monthName(m.month + "-01")}</td>
                      <td className="num py-2 text-right">{litres(m.dispensed_l)}</td>
                      <td className="num py-2 text-right">{litres(m.burned_l)}</td>
                      <td className="num py-2 text-right">{m.ratio == null ? "n/a" : `${Math.round(m.ratio * 100)}%`}</td>
                      <td className="py-2 pl-4 font-mono text-xs uppercase tracking-widest">{m.flagged ? "Look into this" : "Fine"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              </div>
            )}
            <p className="mt-2 text-sm text-ink-soft">Marked when a machine was handed {Math.round((r.settings.ratio_limit - 1) * 100)}% or more above what it burned, and at least {litres(r.settings.min_litres)} litres.</p>
          </>
        )}
      </section>

      <WorkingSheet opened={opened} onClose={() => setOpened(null)} />
      <DiagnosisPanel finding={diagnosing} onClose={() => setDiagnosing(null)} />
    </div>
  );
}
