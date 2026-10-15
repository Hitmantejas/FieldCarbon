import { useState } from "react";
import type { Figure } from "../api";
import { query, useApi } from "../api";
import { SectionHead } from "../components/SectionHead";
import { Stamp } from "../components/Stamp";
import { WorkingSheet, type Opened } from "../components/WorkingSheet";
import type { FleetSummary, Jobs as JobsData } from "../fleetApi";
import { litres, tonnes } from "../format";

const PAGE = 25;
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const monthName = (key: string) => `${MONTHS[Number(key.slice(5)) - 1]} ${key.slice(0, 4)}`;
const dateText = (iso: string) => `${Number(iso.slice(8))} ${MONTHS[Number(iso.slice(5, 7)) - 1]} ${iso.slice(0, 4)}`;

type Filters = { site_id: string; month: string; operation_code: string; client_id: string; machine_id: string };
const NONE: Filters = { site_id: "", month: "", operation_code: "", client_id: "", machine_id: "" };

function Loading({ what }: { what: string }) {
  return <p className="font-mono text-sm uppercase tracking-widest text-ink-soft">Loading {what}...</p>;
}

function Pick({ label, value, onChange, options }: { label: string; value: string; onChange: (v: string) => void; options: { key: string; name: string }[] }) {
  return (
    <label className="flex flex-col gap-2 text-sm text-ink-soft">
      {label}
      <select value={value} onChange={(e) => onChange(e.target.value)} className="min-h-11 min-w-40 border-2 border-ink bg-paper px-2 font-sans text-base normal-case tracking-normal text-ink">
        <option value="">All</option>
        {options.map((o) => (
          <option key={o.key} value={o.key}>
            {o.name}
          </option>
        ))}
      </select>
    </label>
  );
}

export function Jobs() {
  const [tab, setTab] = useState<"jobs" | "fields">("jobs");
  const [f, setF] = useState<Filters>(NONE);
  const [sort, setSort] = useState<"date" | "litres" | "hours">("date");
  const [page, setPage] = useState(0);
  const [showAllFields, setShowAllFields] = useState(false);
  const [opened, setOpened] = useState<Opened | null>(null);

  const sites = useApi<FleetSummary>("/api/fleet/summary?group_by=site");
  const months = useApi<FleetSummary>("/api/fleet/summary?group_by=month");
  const ops = useApi<FleetSummary>("/api/fleet/summary?group_by=operation");
  const clients = useApi<FleetSummary>("/api/fleet/summary?group_by=client");
  const machines = useApi<FleetSummary>("/api/fleet/summary?group_by=machine");
  const jobs = useApi<JobsData>(`/api/fleet/jobs${query({ ...f, sort, limit: PAGE, offset: page * PAGE })}`);
  const fields = useApi<FleetSummary>(`/api/fleet/summary${query({ group_by: "field", site_id: f.site_id || undefined })}`);

  const set = (k: keyof Filters) => (v: string) => {
    setF((x) => ({ ...x, [k]: v }));
    setPage(0);
  };
  const open = (title: string, shown: string, fig: Figure) => setOpened({ title, shown, label: fig.label, how: fig.how, sourceIds: fig.source_ids });
  const names = (d?: FleetSummary, skip?: (k: string) => boolean) => (d?.rows ?? []).filter((r) => !skip?.(r.key)).map((r) => ({ key: r.key, name: r.name }));
  const total = jobs.data?.total_jobs ?? 0;
  const first = total ? page * PAGE + 1 : 0;
  const last = Math.min(total, (page + 1) * PAGE);
  const fieldRows = fields.data?.rows ?? [];
  const shownFields = showAllFields ? fieldRows : fieldRows.slice(0, PAGE);

  return (
    <div className="space-y-10 pb-10">
      <section className="px-6 pt-6" aria-labelledby="h-jobs">
        <h1 id="h-jobs" className="rise font-display text-5xl font-semibold leading-[1.02] sm:text-6xl tracking-tight" style={{ "--i": 1 } as React.CSSProperties}>
          Jobs &amp; fields
        </h1>
        <p className="mt-3 max-w-[70ch] text-ink-soft">
          Every job the fleet did, and the fields it was done on. Narrow the list with the filters, then open a figure to see how it was worked
          out. Job dates in this demo are assigned, not recorded.
        </p>
        <div role="group" aria-label="Jobs or fields" className="mt-4 flex gap-2 text-sm">
          {(["jobs", "fields"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              aria-pressed={tab === t}
              className={`btn-tab min-h-11 border-2 px-4 ${tab === t ? "border-ink bg-ink font-bold text-paper" : "border-rule hover:border-ink"}`}
            >
              {t === "jobs" ? "Jobs" : "Fields"}
            </button>
          ))}
        </div>
      </section>

      <section className="px-6" aria-label="Filters">
        <div className="flex flex-wrap items-end gap-4">
          <Pick label="Site" value={f.site_id} onChange={set("site_id")} options={names(sites.data)} />
          {tab === "jobs" && (
            <>
              <Pick label="Month" value={f.month} onChange={set("month")} options={(months.data?.rows ?? []).map((r) => ({ key: r.key, name: monthName(r.key) }))} />
              <Pick label="Job" value={f.operation_code} onChange={set("operation_code")} options={names(ops.data, (k) => k.startsWith("other_"))} />
              <Pick label="Client" value={f.client_id} onChange={set("client_id")} options={names(clients.data, (k) => k === "unassigned")} />
              <Pick label="Machine" value={f.machine_id} onChange={set("machine_id")} options={names(machines.data)} />
            </>
          )}
          <button
            onClick={() => {
              setF(NONE);
              setPage(0);
            }}
            className="btn-outline min-h-11 border-2 border-ink px-4 text-sm font-bold"
          >
            Clear filters
          </button>
        </div>
      </section>

      {tab === "jobs" ? (
        <section className="px-6" aria-labelledby="h-list">
          <SectionHead
            id="h-list"
            title="Jobs"
            tone="mark"
            note={jobs.data?.totals ? `${litres(total)} jobs · ${litres(jobs.data.totals.litres.value ?? 0)} L · ${tonnes(jobs.data.totals.co2e_kg.value ?? 0)} CO2e` : undefined}
            aside={
              <label className="flex items-center gap-2 font-mono text-xs uppercase tracking-widest">
                Sort by
                <select
                  value={sort}
                  onChange={(e) => {
                    setSort(e.target.value as typeof sort);
                    setPage(0);
                  }}
                  className="min-h-11 border-2 border-ink bg-paper px-2 font-sans text-base normal-case tracking-normal"
                >
                  <option value="date">Date</option>
                  <option value="litres">Most fuel</option>
                  <option value="hours">Longest</option>
                </select>
              </label>
            }
          />
          {!jobs.data ? (
            <Loading what="jobs" />
          ) : jobs.data.rows.length === 0 ? (
            <p>No jobs match these filters.</p>
          ) : (
            <>
              <div className="overflow-x-auto">
              <table className="w-full text-left">
                <caption className="sr-only">Jobs with their fuel and emissions</caption>
                <thead>
                  <tr className="border-b-2 border-rule font-mono text-xs uppercase tracking-widest text-ink-soft">
                    <th scope="col" className="px-2 py-3 pl-0 font-normal">Date</th>
                    <th scope="col" className="px-2 py-3 font-normal">Job</th>
                    <th scope="col" className="px-2 py-3 font-normal">Machine</th>
                    <th scope="col" className="px-2 py-3 font-normal">Client</th>
                    <th scope="col" className="px-2 py-3 font-normal">Field</th>
                    <th scope="col" className="px-2 py-3 text-right font-normal">Hours</th>
                    <th scope="col" className="px-2 py-3 text-right font-normal">Fuel (litres)</th>
                    <th scope="col" className="px-2 py-3 text-right font-normal">Litres per ha</th>
                    <th scope="col" className="px-2 py-3 pr-0 font-normal">Label</th>
                  </tr>
                </thead>
                <tbody>
                  {jobs.data.rows.map((j) => (
                    <tr key={j.job_id} className="border-b border-rule transition-colors hover:bg-mark/20">
                      <th scope="row" className="whitespace-nowrap px-2 py-3 pl-0 font-normal">{dateText(j.date)}</th>
                      <td className="px-2 py-3 font-bold">{j.operation}</td>
                      <td className="px-2 py-3">{j.machine}</td>
                      <td className="whitespace-nowrap px-2 py-3">{j.client ?? <span className="text-ink-soft">Field not matched</span>}</td>
                      <td className="whitespace-nowrap px-2 py-3">{j.field ?? <span className="text-ink-soft">None</span>}</td>
                      <td className="num px-2 py-3 text-right">{j.hours.toFixed(1)}</td>
                      <td className="num px-2 py-3 text-right">
                        <button onClick={() => open(`${j.operation}, ${dateText(j.date)}`, `${j.litres.value?.toFixed(1)} L`, j.litres)} className="btn-link underline underline-offset-4">
                          {(j.litres.value ?? 0).toFixed(1)}
                        </button>
                      </td>
                      <td className="num px-2 py-3 text-right">
                        {j.l_per_ha ? (
                          <button onClick={() => open(`Litres per hectare, ${j.operation}`, `${j.l_per_ha!.value?.toFixed(1)} L/ha`, j.l_per_ha!)} className="btn-link underline underline-offset-4">
                            {(j.l_per_ha.value ?? 0).toFixed(1)}
                          </button>
                        ) : (
                          <span className="text-ink-soft">n/a</span>
                        )}
                      </td>
                      <td className="px-2 py-3 pr-0"><Stamp label={j.litres.label} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
              </div>
              <nav aria-label="Pages" className="mt-4 flex flex-wrap items-center gap-3 font-mono text-xs uppercase tracking-widest">
                <button disabled={page === 0} onClick={() => setPage((p) => p - 1)} className="btn-outline min-h-11 border-2 border-ink px-4 disabled:opacity-40">
                  Previous
                </button>
                <span aria-live="polite">
                  {first} to {last} of {litres(total)}
                </span>
                <button disabled={last >= total} onClick={() => setPage((p) => p + 1)} className="btn-outline min-h-11 border-2 border-ink px-4 disabled:opacity-40">
                  Next
                </button>
              </nav>
            </>
          )}
        </section>
      ) : (
        <section className="px-6" aria-labelledby="h-fields">
          <SectionHead id="h-fields" title="Fields" tone="dashed" note="fuel burned working each field" />
          <p className="mb-4 max-w-[75ch] text-ink-soft">
            Fuel burned outside jobs, such as travel and idling, belongs to no field, so it is not counted here. Arable field figures are
            allocated: the litres are measured, but which field a job was on comes from matching GPS positions to field outlines.
          </p>
          {!fields.data ? (
            <Loading what="fields" />
          ) : (
            <>
              <div className="overflow-x-auto">
              <table className="w-full text-left">
                <caption className="sr-only">Fuel and emissions by field</caption>
                <thead>
                  <tr className="border-b-2 border-rule font-mono text-xs uppercase tracking-widest text-ink-soft">
                    <th scope="col" className="px-3 py-3 pl-0 font-normal">Field</th>
                    <th scope="col" className="px-3 py-3 text-right font-normal">Fuel (litres)</th>
                    <th scope="col" className="px-3 py-3 text-right font-normal">Emissions</th>
                    <th scope="col" className="px-3 py-3 text-right font-normal">Jobs</th>
                    <th scope="col" className="px-3 py-3 text-right font-normal">Hectares</th>
                    <th scope="col" className="px-3 py-3 pr-0 font-normal">Label</th>
                  </tr>
                </thead>
                <tbody>
                  {shownFields.map((r) => (
                    <tr key={r.key} className="border-b border-rule transition-colors hover:bg-mark/20">
                      <th scope="row" className="px-3 py-3 pl-0 font-bold">
                        <button onClick={() => open(r.name, `${litres(r.litres.value ?? 0)} L`, r.litres)} className="btn-link text-left underline underline-offset-4">
                          {r.name}
                        </button>
                        <span className="block font-mono text-xs font-normal uppercase tracking-widest text-ink-soft">
                          {sites.data?.rows.find((s) => s.key === r.key.slice(0, 2))?.name}
                        </span>
                      </th>
                      <td className="num px-3 py-3 text-right">{litres(r.litres.value ?? 0)}</td>
                      <td className="num px-3 py-3 text-right">{tonnes(r.co2e_kg.value ?? 0)}</td>
                      <td className="num px-3 py-3 text-right">{litres(r.jobs)}</td>
                      <td className="num px-3 py-3 text-right">{litres(r.area_ha)}</td>
                      <td className="px-3 py-3 pr-0"><Stamp label={r.litres.label} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
              </div>
              {fieldRows.length > PAGE && (
                <button onClick={() => setShowAllFields((v) => !v)} aria-pressed={showAllFields} className="btn-outline mt-4 min-h-11 border-2 border-ink px-4 text-sm font-bold">
                  {showAllFields ? "Show only the top 25" : `Show all ${fieldRows.length} fields`}
                </button>
              )}
            </>
          )}
        </section>
      )}

      <WorkingSheet opened={opened} onClose={() => setOpened(null)} />
    </div>
  );
}
