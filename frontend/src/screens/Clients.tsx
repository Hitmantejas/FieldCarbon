import { Fragment, useState } from "react";
import type { Figure } from "../api";
import { useApi } from "../api";
import { SectionHead } from "../components/SectionHead";
import { Stamp } from "../components/Stamp";
import { Tile } from "../components/Tile";
import { WorkingSheet, type Opened } from "../components/WorkingSheet";
import type { ClientEmissions } from "../fleetApi";
import { gbpFull, litres, tonnes } from "../format";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const monthName = (key: string) => `${MONTHS[Number(key.slice(5)) - 1]} ${key.slice(0, 4)}`;

function Loading({ what }: { what: string }) {
  return <p className="font-mono text-sm uppercase tracking-widest text-ink-soft">Loading {what}...</p>;
}

// One client's emissions month by month: the figures a client asks for in its own reporting.
function ClientMonths({ id, name, open }: { id: string; name: string; open: (title: string, shown: string, f: Figure) => void }) {
  const detail = useApi<ClientEmissions>(`/api/fleet/clients?client_id=${id}`);
  if (!detail.data) return <Loading what="months" />;
  const months = detail.data.months;
  const top = Math.max(1, ...months.map((m) => m.co2e_kg.value ?? 0));
  return (
    <div className="space-y-4">
      <p className="font-bold">{name}: emissions by month</p>
      <ol className="space-y-2">
        {months.map((m) => (
          <li key={m.month} className="grid grid-cols-[6.5rem_1fr_7rem_8rem] items-center gap-4">
            <span className="font-mono text-xs uppercase tracking-widest text-ink-soft">{monthName(m.month)}</span>
            <div className="h-3 overflow-hidden rounded-full bg-tint" role="img" aria-label={`${monthName(m.month)}: ${tonnes(m.co2e_kg.value ?? 0)} of CO2e`}>
              <div className="span-in h-full rounded-full bg-moss" style={{ width: `${((m.co2e_kg.value ?? 0) / top) * 100}%` }} />
            </div>
            <button
              onClick={() => open(`${name}, ${monthName(m.month)}`, `${tonnes(m.co2e_kg.value ?? 0)} CO2e`, m.co2e_kg)}
              className="btn-link num text-right underline underline-offset-4"
            >
              {tonnes(m.co2e_kg.value ?? 0)}
            </button>
            <span className="num text-right text-ink-soft">{litres(m.litres.value ?? 0)} L</span>
          </li>
        ))}
      </ol>
    </div>
  );
}

export function Clients() {
  const clients = useApi<ClientEmissions>("/api/fleet/clients");
  const [picked, setPicked] = useState<string | null>(null);
  const [opened, setOpened] = useState<Opened | null>(null);

  const open = (title: string, shown: string, f: Figure) => setOpened({ title, shown, label: f.label, how: f.how, sourceIds: f.source_ids });
  const rows = clients.data?.rows ?? [];
  const overhead = clients.data?.overhead;
  const unmatched = clients.data?.unmatched_jobs;
  const total = clients.data?.total;

  return (
    <div className="space-y-10 pb-10">
      <section className="px-6 pt-6" aria-labelledby="h-clients">
        <h1 id="h-clients" className="rise font-display text-6xl font-semibold leading-[1.02] tracking-tight" style={{ "--i": 1 } as React.CSSProperties}>
          Clients
        </h1>
        <p className="mt-3 max-w-[70ch] text-ink-soft">
          Fuel and emissions for the work done on each client farm. Clients ask for these figures for their own reporting. Open a client to see
          its months, and use the working sheet to show how each figure was worked out.
        </p>
      </section>

      {!clients.data ? (
        <div className="px-6">
          <Loading what="clients" />
        </div>
      ) : (
        <section aria-label="Client totals" className="mx-6 grid gap-3 sm:grid-cols-3">
          <Tile title="Client farms" shown={String(rows.length)} unit="served" />
          {total && <Tile title="Fleet fuel" shown={litres(total.value ?? 0)} unit="L" figure={total} onOpen={() => open("Fleet fuel", `${litres(total.value ?? 0)} L`, total)} />}
          {overhead && (
            <Tile
              title="Company overhead"
              shown={litres(overhead.litres.value ?? 0)}
              unit="L"
              figure={overhead.litres}
              onOpen={() => open("Company overhead", `${litres(overhead.litres.value ?? 0)} L`, overhead.litres)}
              highlight
            />
          )}
        </section>
      )}

      <section className="px-6" aria-labelledby="h-table">
        <SectionHead id="h-table" title="Emissions per client farm" tone="mark" note="open a client for its months" />
        {!clients.data ? (
          <Loading what="clients" />
        ) : (
          <table className="w-full text-left">
            <caption className="sr-only">Fuel, emissions and cost by client farm</caption>
            <thead>
              <tr className="border-b-2 border-rule font-mono text-xs uppercase tracking-widest text-ink-soft">
                <th scope="col" className="px-3 py-3 pl-0 font-normal">Client</th>
                <th scope="col" className="px-3 py-3 text-right font-normal">Fuel (litres)</th>
                <th scope="col" className="px-3 py-3 text-right font-normal">Emissions</th>
                <th scope="col" className="px-3 py-3 text-right font-normal">Fuel cost</th>
                <th scope="col" className="px-3 py-3 text-right font-normal">Jobs</th>
                <th scope="col" className="px-3 py-3 text-right font-normal">Hectares</th>
                <th scope="col" className="px-3 py-3 pr-0 font-normal">Label</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const isOpen = picked === r.client_id;
                return (
                  <Fragment key={r.client_id}>
                    <tr className={`border-b border-rule transition-colors ${isOpen ? "bg-mark/20" : "hover:bg-mark/20"}`}>
                      <th scope="row" className="px-3 py-4 pl-0 font-bold">
                        <button onClick={() => setPicked(isOpen ? null : r.client_id)} aria-expanded={isOpen} className="btn-link text-left underline underline-offset-4">
                          {r.name}
                        </button>
                      </th>
                      <td className="num px-3 py-4 text-right">{litres(r.litres.value ?? 0)}</td>
                      <td className="num px-3 py-4 text-right">{tonnes(r.co2e_kg.value ?? 0)}</td>
                      <td className="num px-3 py-4 text-right">{gbpFull(r.cost_gbp.value ?? 0)}</td>
                      <td className="num px-3 py-4 text-right">{litres(r.jobs)}</td>
                      <td className="num px-3 py-4 text-right">{litres(r.area_ha)}</td>
                      <td className="px-3 py-4 pr-0"><Stamp label={r.litres.label} /></td>
                    </tr>
                    {isOpen && (
                      <tr className="border-b border-rule">
                        <td colSpan={7} className="px-0 py-5">
                          <div className="space-y-4">
                            <ClientMonths id={r.client_id} name={r.name} open={open} />
                            <div className="no-print flex flex-wrap gap-3">
                              <button onClick={() => open(r.name, `${litres(r.litres.value ?? 0)} L`, r.litres)} className="btn-outline min-h-11 border-2 border-ink px-4 text-sm font-bold">
                                How this was worked out
                              </button>
                              <button onClick={() => window.print()} className="btn-outline min-h-11 border-2 border-ink px-4 text-sm font-bold">
                                Print or save as PDF
                              </button>
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        )}
      </section>

      {overhead && (
        <section className="px-6" aria-labelledby="h-overhead">
          <SectionHead id="h-overhead" title="Company overhead" tone="dashed" note="not charged to a client" />
          <div className="mb-5 max-w-[75ch] space-y-2">
            <p>
              Fuel burned between and around jobs. No client's field is being worked, so it belongs to the company. It also adds up: client farms,
              overhead and any unmatched jobs together make the fleet total{total ? ` of ${litres(total.value ?? 0)} litres` : ""}.
            </p>
            <p className="text-ink-soft">This is the part the company controls most: less idling, fewer trips, fewer passes with a tool attached but not working.</p>
          </div>
          <ol className="space-y-3">
            {overhead.breakdown.map((b) => (
              <li key={b.key} className="grid grid-cols-[minmax(12rem,18rem)_1fr_8rem_8rem] items-center gap-4">
                <span>{b.name}</span>
                <div className="h-3 overflow-hidden rounded-full bg-tint" role="img" aria-label={`${b.name}: ${litres(b.litres.value ?? 0)} litres`}>
                  <div className="span-in h-full rounded-full bg-moss" style={{ width: `${((b.litres.value ?? 0) / Math.max(1, overhead.litres.value ?? 1)) * 100}%` }} />
                </div>
                <button onClick={() => open(b.name, `${litres(b.litres.value ?? 0)} L`, b.litres)} className="btn-link num text-right underline underline-offset-4">
                  {litres(b.litres.value ?? 0)} L
                </button>
                <Stamp label={b.litres.label} />
              </li>
            ))}
          </ol>
          {unmatched && (
            <p className="mt-6 max-w-[75ch] border-l-4 border-mark pl-4">
              <strong>
                {litres(unmatched.litres.value ?? 0)} litres from {unmatched.jobs} jobs
              </strong>{" "}
              could not be matched to a field, so they are in no client's figures.{" "}
              <button onClick={() => open("Jobs with no matched field", `${litres(unmatched.litres.value ?? 0)} L`, unmatched.litres)} className="btn-link underline underline-offset-4">
                How this was worked out
              </button>
            </p>
          )}
        </section>
      )}

      <WorkingSheet opened={opened} onClose={() => setOpened(null)} />
    </div>
  );
}
