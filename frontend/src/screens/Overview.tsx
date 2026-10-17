import { useState } from "react";
import type { Figure, Label } from "../api";
import { useApi } from "../api";
import { Briefing } from "../components/Briefing";
import { FindingList } from "../components/FindingList";
import { RangeBar } from "../components/RangeBar";
import { SectionHead } from "../components/SectionHead";
import { Stamp } from "../components/Stamp";
import { Tile } from "../components/Tile";
import { WorkingSheet, type Opened } from "../components/WorkingSheet";
import type { Anomalies, FleetOpportunities, FleetSummary, Reconciliation, Severity } from "../fleetApi";
import { gbpFull, litres, tonnes } from "../format";
import { co2Text } from "../ranges";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const monthName = (key: string) => `${MONTHS[Number(key.slice(5)) - 1]} ${key.slice(2, 4)}`;
const LABEL_ORDER: Label[] = ["measured", "allocated", "estimated"];
const SEVERITY_ORDER: Record<Severity, number> = { high: 0, medium: 1, low: 2 };

function Loading({ what }: { what: string }) {
  return <p className="px-6 py-8 font-mono text-sm uppercase tracking-widest text-ink-soft">Loading {what}...</p>;
}

export function Overview() {
  const sites = useApi<FleetSummary>("/api/fleet/summary?group_by=site");
  const months = useApi<FleetSummary>("/api/fleet/summary?group_by=month");
  const anomalies = useApi<Anomalies>("/api/fleet/anomalies");
  const recon = useApi<Reconciliation>("/api/fleet/reconciliation");
  const ideas = useApi<FleetOpportunities>("/api/fleet/opportunities");
  const [opened, setOpened] = useState<Opened | null>(null);

  const open = (title: string, shown: string, f: Figure) =>
    setOpened({ title, shown, label: f.label, how: f.how, sourceIds: f.source_ids });

  const t = sites.data?.totals;
  const watch = [...(recon.data?.findings ?? []), ...(anomalies.data?.findings ?? [])]
    .sort((a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity])
    .slice(0, 5);
  const feasible = (ideas.data?.ideas ?? []).filter((i) => i.state === "feasible" && i.figures.co2e_avoided_kg?.low != null);
  const maxSaved = Math.max(1, ...feasible.map((i) => i.figures.co2e_avoided_kg?.high ?? 0));
  const monthRows = months.data?.rows ?? [];
  const maxMonth = Math.max(1, ...monthRows.map((m) => m.litres.value ?? 0));
  // One label for the whole chart: the weakest of the months' labels.
  const monthLabel = monthRows.map((m) => m.litres.label).sort((a, b) => LABEL_ORDER.indexOf(b) - LABEL_ORDER.indexOf(a))[0];

  return (
    <div className="space-y-10 pb-10">
      <section className="px-6 pt-6" aria-labelledby="h-fleet">
        <h1 id="h-fleet" className="rise font-display text-5xl font-semibold leading-[1.02] sm:text-6xl tracking-tight" style={{ "--i": 1 } as React.CSSProperties}>
          {t ? `${litres(t.litres.value ?? 0)} litres burned.` : "Fleet overview"}
          <br />
          {watch.length > 0 && <span className="text-moss">{watch.length} things to look at.</span>}
        </h1>
        {t && (
          <p className="mt-3 max-w-[70ch] text-ink-soft">
            {litres(t.jobs)} jobs over {litres(t.hours)} engine hours on {sites.data?.rows.length} sites. Totals come from the machines; splits by
            site, job and month are shared by rule; savings are always ranges.
          </p>
        )}
      </section>

      {!t ? (
        <Loading what="fleet figures" />
      ) : (
        <section aria-label="Fleet totals" className="mx-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Tile title="Fuel" shown={litres(t.litres.value ?? 0)} unit="L" figure={t.litres} onOpen={() => open("Fuel burned", `${litres(t.litres.value ?? 0)} L`, t.litres)} />
          <Tile title="Emissions" shown={tonnes(t.co2e_kg.value ?? 0).replace(" t", "")} unit="t CO2e" figure={t.co2e_kg} onOpen={() => open("Emissions", tonnes(t.co2e_kg.value ?? 0) + " CO2e", t.co2e_kg)} />
          <Tile title="Fuel cost" shown={gbpFull(t.cost_gbp.value ?? 0)} unit="" figure={t.cost_gbp} onOpen={() => open("Fuel cost", gbpFull(t.cost_gbp.value ?? 0), t.cost_gbp)} />
          <Tile title="To look at" shown={String(watch.length)} unit="findings" highlight />
        </section>
      )}

      <Briefing onOpen={open} />

      <section className="px-6" aria-labelledby="h-watch">
        <SectionHead id="h-watch" title="Worth a look" tone="mark" note="to investigate, not proof of a fault" />
        {!anomalies.data || !recon.data ? (
          <Loading what="findings" />
        ) : (
          <FindingList findings={watch} onOpen={open} />
        )}
      </section>

      <div className="grid gap-10 px-6 xl:grid-cols-2">
        <section aria-labelledby="h-sites">
          <SectionHead id="h-sites" title="By site" tone="solid" />
          {!sites.data ? (
            <Loading what="sites" />
          ) : (
            <div className="overflow-x-auto">
            <table className="w-full text-left">
              <caption className="sr-only">Fuel, emissions and cost by site</caption>
              <thead>
                <tr className="border-b-2 border-rule font-mono text-xs uppercase tracking-widest text-ink-soft">
                  <th scope="col" className="py-2 font-normal">Site</th>
                  <th scope="col" className="py-2 text-right font-normal">Litres</th>
                  <th scope="col" className="py-2 text-right font-normal">CO2e</th>
                  <th scope="col" className="py-2 pl-4 font-normal">Label</th>
                </tr>
              </thead>
              <tbody>
                {sites.data.rows.map((r) => (
                  <tr key={r.key} className="border-b border-rule transition-colors hover:bg-mark/20">
                    <th scope="row" className="py-3 pr-2 font-bold">
                      <button onClick={() => open(r.name, `${litres(r.litres.value ?? 0)} L`, r.litres)} className="btn-link text-left underline underline-offset-4">
                        {r.name}
                      </button>
                    </th>
                    <td className="num py-3 text-right">{litres(r.litres.value ?? 0)}</td>
                    <td className="num py-3 text-right">{tonnes(r.co2e_kg.value ?? 0)}</td>
                    <td className="py-3 pl-4"><Stamp label={r.litres.label} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
          )}
        </section>

        <section aria-labelledby="h-months">
          <SectionHead id="h-months" title="By month" tone="dashed" aside={monthLabel && <Stamp label={monthLabel} />} />
          {monthRows.length === 0 ? (
            <Loading what="months" />
          ) : (
            <ol className="space-y-1">
              {monthRows.map((m) => (
                <li key={m.key} className="grid grid-cols-[4.5rem_1fr_5.5rem] items-center gap-3">
                  <span className="font-mono text-xs uppercase tracking-widest text-ink-soft">{monthName(m.key)}</span>
                  <div className="h-3 overflow-hidden rounded-full bg-tint" role="img" aria-label={`${monthName(m.key)}: ${litres(m.litres.value ?? 0)} litres`}>
                    <div className="span-in h-full rounded-full bg-moss" style={{ width: `${((m.litres.value ?? 0) / maxMonth) * 100}%` }} />
                  </div>
                  <span className="num text-right text-sm">{litres(m.litres.value ?? 0)} L</span>
                </li>
              ))}
            </ol>
          )}
        </section>
      </div>

      <section className="px-6" aria-labelledby="h-ideas">
        <SectionHead id="h-ideas" title="Ideas that suit the arable sites" tone="solid" note="CO2e avoided a year · ranges from research · never added together" />
        {!ideas.data ? (
          <Loading what="ideas" />
        ) : (
          <ul className="divide-y divide-rule">
            {feasible.map((i) => {
              const f = i.figures.co2e_avoided_kg!;
              const one = f.low === f.high; // one study figure, so no range to show
              const shown = co2Text(f).replace(" CO2e", "");
              return (
                <li key={i.intervention_id} className="grid items-center gap-4 py-3 md:grid-cols-[16rem_1fr_11rem]">
                  <div>
                    <p className="font-bold">{i.name}</p>
                    <p className="font-mono text-xs uppercase tracking-widest text-ink-soft">
                      {i.robustness} evidence · {i.n_sources} {i.n_sources === 1 ? "source" : "sources"}
                    </p>
                  </div>
                  <RangeBar low={f.low ?? 0} high={f.high ?? 0} max={maxSaved} description={`${i.name}: ${shown} of CO2e a year`} />
                  <button
                    onClick={() => open(i.name, `${shown} CO2e a year`, f)}
                    className="btn-link flex flex-col items-start gap-1 text-left"
                    aria-label={`${i.name}: ${shown} of CO2e a year${one ? ", one figure from the research, no range" : ""}, ${f.label}. Show how it was worked out.`}
                  >
                    <span className="num text-sm underline underline-offset-4">{shown}</span>
                    {one && <span className="font-mono text-xs uppercase tracking-widest text-ink-soft">single figure</span>}
                    <Stamp label={f.label} />
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <WorkingSheet opened={opened} onClose={() => setOpened(null)} />
    </div>
  );
}
