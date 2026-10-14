import { Fragment, useState } from "react";
import type { Figure } from "../api";
import { useApi } from "../api";
import { SectionHead } from "../components/SectionHead";
import { Stamp } from "../components/Stamp";
import { WorkingSheet, type Opened } from "../components/WorkingSheet";
import type { DataQuality, FleetSummary, GroupRow } from "../fleetApi";
import { litres, tonnes } from "../format";

const DATA_KIND: Record<string, string> = {
  "raw telemetry": "Engine data recorded second by second.",
  "per-operation summary": "One record per job. Fuel comes from the tank level.",
  "raw telemetry, tillage only": "Engine data for ploughing and tilling only.",
};

function Loading({ what }: { what: string }) {
  return <p className="font-mono text-sm uppercase tracking-widest text-ink-soft">Loading {what}...</p>;
}

// What one machine spent its fuel on, so a manager can see where its litres went.
function MachineDetail({ machine, open }: { machine: GroupRow; open: (title: string, shown: string, f: Figure) => void }) {
  const ops = useApi<FleetSummary>(`/api/fleet/summary?group_by=operation&machine_id=${machine.key}`);
  if (!ops.data) return <Loading what="jobs" />;
  const top = Math.max(1, ...ops.data.rows.map((r) => r.litres.value ?? 0));
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="font-bold">What {machine.name} spent its fuel on</p>
        <button
          onClick={() => open(machine.name, `${litres(machine.litres.value ?? 0)} L`, machine.litres)}
          className="btn-outline min-h-11 border-2 border-ink px-4 text-sm font-bold"
        >
          How this was worked out
        </button>
      </div>
      <ol className="space-y-2">
        {ops.data.rows.map((r) => (
          <li key={r.key} className="grid grid-cols-[minmax(10rem,16rem)_1fr_9rem_8rem] items-center gap-4">
            <span>{r.name}</span>
            <div className="h-3 overflow-hidden rounded-full bg-tint" role="img" aria-label={`${r.name}: ${litres(r.litres.value ?? 0)} litres`}>
              <div className="span-in h-full rounded-full bg-moss" style={{ width: `${((r.litres.value ?? 0) / top) * 100}%` }} />
            </div>
            <span className="num text-right">{litres(r.litres.value ?? 0)} L</span>
            <Stamp label={r.litres.label} />
          </li>
        ))}
      </ol>
    </div>
  );
}

export function Sites() {
  const sites = useApi<FleetSummary>("/api/fleet/summary?group_by=site");
  const machines = useApi<FleetSummary>("/api/fleet/summary?group_by=machine");
  const quality = useApi<DataQuality>("/api/fleet/data-quality");
  const [site, setSite] = useState("");
  const [picked, setPicked] = useState<string | null>(null);
  const [opened, setOpened] = useState<Opened | null>(null);

  const open = (title: string, shown: string, f: Figure) => setOpened({ title, shown, label: f.label, how: f.how, sourceIds: f.source_ids });
  const rows = (machines.data?.rows ?? []).filter((m) => !site || m.site_id === site);
  const q = quality.data;

  return (
    <div className="space-y-10 pb-10">
      <section className="px-6 pt-6" aria-labelledby="h-sites">
        <h1 id="h-sites" className="rise font-display text-6xl font-semibold leading-[1.02] tracking-tight" style={{ "--i": 1 } as React.CSSProperties}>
          Sites &amp; machines
        </h1>
        <p className="mt-3 max-w-[70ch] text-ink-soft">
          Where the fleet works and which machines burn the fuel. Open a machine to see what it spent its fuel on. The label on each figure says
          how it was obtained: read from the machine, or shared out by rule.
        </p>
      </section>

      <section className="px-6" aria-labelledby="h-site-cards">
        <SectionHead id="h-site-cards" title="Sites" tone="solid" />
        {!sites.data ? (
          <Loading what="sites" />
        ) : (
          <ul className="grid gap-6 lg:grid-cols-3">
            {sites.data.rows.map((r) => (
              <li key={r.key} className="flex flex-col gap-3 rounded-3xl bg-tint p-5">
                <h3 className="font-display text-2xl font-semibold leading-tight">{r.name}</h3>
                <p className="text-ink-soft">{r.data_kind && DATA_KIND[r.data_kind]}</p>
                <button
                  onClick={() => open(r.name, `${litres(r.litres.value ?? 0)} L`, r.litres)}
                  className="btn-link flex items-end gap-3 text-left"
                  aria-label={`${r.name}: ${litres(r.litres.value ?? 0)} litres, ${r.litres.label}. Show how it was worked out.`}
                >
                  <span className="font-display text-5xl font-semibold leading-none">{litres(r.litres.value ?? 0)}</span>
                  <span className="font-mono text-sm">litres</span>
                </button>
                <Stamp label={r.litres.label} />
                <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-6 gap-y-1 font-mono text-sm">
                  <dt className="text-ink-soft">Emissions</dt>
                  <dd className="num">{tonnes(r.co2e_kg.value ?? 0)} CO2e</dd>
                  <dt className="text-ink-soft">Jobs</dt>
                  <dd className="num">{litres(r.jobs)}</dd>
                  <dt className="text-ink-soft">Engine hours</dt>
                  <dd className="num">{litres(r.hours)}</dd>
                  <dt className="text-ink-soft">Worked</dt>
                  <dd className="num">{litres(r.area_ha)} hectares</dd>
                </dl>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="px-6" aria-labelledby="h-machines">
        <SectionHead id="h-machines" title="Machines" tone="mark" note="open a machine to see its fuel by job" />
        <div role="group" aria-label="Which site" className="mb-4 flex flex-wrap gap-2 text-sm">
          {[{ key: "", name: "All sites" }, ...(sites.data?.rows ?? [])].map((s) => (
            <button
              key={s.key}
              onClick={() => {
                setSite(s.key);
                setPicked(null);
              }}
              aria-pressed={site === s.key}
              className={`btn-tab min-h-11 border-2 px-4 ${site === s.key ? "border-ink bg-ink font-bold text-paper" : "border-rule hover:border-ink"}`}
            >
              {s.name}
            </button>
          ))}
        </div>
        {!machines.data ? (
          <Loading what="machines" />
        ) : (
          <table className="w-full text-left">
            <caption className="sr-only">Fuel, emissions and work by machine</caption>
            <thead>
              <tr className="border-b-2 border-rule font-mono text-xs uppercase tracking-widest text-ink-soft">
                <th scope="col" className="px-3 py-3 pl-0 font-normal">Machine</th>
                <th scope="col" className="px-3 py-3 text-right font-normal">Fuel (litres)</th>
                <th scope="col" className="px-3 py-3 text-right font-normal">Share of fleet fuel</th>
                <th scope="col" className="px-3 py-3 text-right font-normal">Emissions</th>
                <th scope="col" className="px-3 py-3 text-right font-normal">Jobs</th>
                <th scope="col" className="px-3 py-3 text-right font-normal">Engine hours</th>
                <th scope="col" className="px-3 py-3 pr-0 font-normal">Label</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((m) => {
                const isOpen = picked === m.key;
                return (
                  <Fragment key={m.key}>
                    <tr className={`border-b border-rule transition-colors ${isOpen ? "bg-mark/20" : "hover:bg-mark/20"}`}>
                      <th scope="row" className="px-3 py-4 pl-0 font-bold">
                        <button onClick={() => setPicked(isOpen ? null : m.key)} aria-expanded={isOpen} className="btn-link text-left underline underline-offset-4">
                          {m.name}
                        </button>
                        <span className="block font-mono text-xs font-normal uppercase tracking-widest text-ink-soft">
                          {sites.data?.rows.find((s) => s.key === m.site_id)?.name}
                        </span>
                      </th>
                      <td className="num px-3 py-4 text-right">{litres(m.litres.value ?? 0)}</td>
                      <td className="num px-3 py-4 text-right">{m.share_pct.toFixed(1)}%</td>
                      <td className="num px-3 py-4 text-right">{tonnes(m.co2e_kg.value ?? 0)}</td>
                      <td className="num px-3 py-4 text-right">{litres(m.jobs)}</td>
                      <td className="num px-3 py-4 text-right">{litres(m.hours)}</td>
                      <td className="px-3 py-4 pr-0"><Stamp label={m.litres.label} /></td>
                    </tr>
                    {isOpen && (
                      <tr className="border-b border-rule">
                        <td colSpan={7} className="px-0 py-5">
                          <MachineDetail machine={m} open={open} />
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

      <section className="px-6" aria-labelledby="h-trust">
        <SectionHead id="h-trust" title="How far to trust this data" tone="dashed" />
        {!q ? (
          <Loading what="data checks" />
        ) : (
          <ul className="grid gap-6 md:grid-cols-2 xl:grid-cols-4">
            {[
              { title: "Fuel read from the machines", shown: `${q.measured_share_pct.value?.toFixed(0)}%`, f: q.measured_share_pct },
              { title: "Fuel charged to no client", shown: `${litres(q.unassigned_litres.value ?? 0)} L`, f: q.unassigned_litres },
              { title: "Hours left out (frozen recorder)", shown: `${litres(q.frozen_hours.value ?? 0)} h`, f: q.frozen_hours },
              { title: "Jobs with no area", shown: `${litres(q.jobs_without_area.value ?? 0)}`, f: q.jobs_without_area },
            ].map((c) => (
              <li key={c.title}>
                <button
                  onClick={() => open(c.title, c.shown, c.f)}
                  aria-label={`${c.title}: ${c.shown}, ${c.f.label}. Show how it was worked out.`}
                  className="flex h-full w-full flex-col justify-between gap-3 rounded-3xl bg-tint p-4 text-left transition-colors hover:bg-mark/40"
                >
                  <span className="font-mono text-xs uppercase tracking-widest">{c.title}</span>
                  <span className="font-display text-4xl font-semibold leading-none">{c.shown}</span>
                  <Stamp label={c.f.label} />
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <WorkingSheet opened={opened} onClose={() => setOpened(null)} />
    </div>
  );
}
