import { useState } from "react";
import type { Figure } from "../api";
import { useApi } from "../api";
import { FindingList, SeverityTag } from "../components/FindingList";
import { SectionHead } from "../components/SectionHead";
import { Stamp } from "../components/Stamp";
import { WorkingSheet, type Opened } from "../components/WorkingSheet";
import type { Anomalies, DeliveryNotes, DepotMonth, NoteFinding, Reconciliation, Severity } from "../fleetApi";
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
              <span className="flex items-center gap-3">
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
              <button onClick={() => onOpen(f.title, amount(f.figure!), f.figure!)} className="btn-row grid w-[calc(100%+1rem)] grid-cols-[5.5rem_1fr_auto] items-center gap-4 py-3 text-left">
                {row}
              </button>
            ) : (
              <div className="grid grid-cols-[5.5rem_1fr_auto] items-center gap-4 py-3">{row}</div>
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

export function FuelControl() {
  const recon = useApi<Reconciliation>("/api/fleet/reconciliation");
  const anomalies = useApi<Anomalies>("/api/fleet/anomalies");
  const notes = useApi<DeliveryNotes>("/api/fleet/delivery-notes");
  const [opened, setOpened] = useState<Opened | null>(null);
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
        <h1 id="h-control" className="rise font-display text-6xl font-semibold leading-[1.02] tracking-tight" style={{ "--i": 1 } as React.CSSProperties}>
          Fuel control
        </h1>
        <p className="mt-3 max-w-[70ch] text-ink-soft">
          Fuel handed out against fuel burned, each depot's books against its tank, and things in the machines' own data that look odd. Each one is
          a reason to investigate, not proof of a fault or a loss.
        </p>
      </section>

      <section className="px-6" aria-labelledby="h-recon">
        <SectionHead id="h-recon" title="Fuel that does not add up" tone="mark" aside={r && <HowButton onClick={() => openChecked("Fuel that does not add up", r.depots)} label="the depot check" />} />
        {!r ? <Loading what="reconciliation" /> : r.findings.length === 0 ? <p>Nothing found.</p> : <FindingList findings={bySeverity(r.findings)} onOpen={open} />}
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
      </section>

      <section className="px-6" aria-labelledby="h-odd">
        <SectionHead id="h-odd" title="Odd in the machines' data" tone="dashed" />
        {!anomalies.data ? <Loading what="machine findings" /> : <FindingList findings={anomalies.data.findings} onOpen={open} />}
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
            )}
            <p className="mt-2 text-sm text-ink-soft">Marked when a machine was handed {Math.round((r.settings.ratio_limit - 1) * 100)}% or more above what it burned, and at least {litres(r.settings.min_litres)} litres.</p>
          </>
        )}
      </section>

      <WorkingSheet opened={opened} onClose={() => setOpened(null)} />
    </div>
  );
}
