import { useState } from "react";
import { query, useApi } from "../api";
import { Rich } from "../components/Rich";
import { SectionHead } from "../components/SectionHead";
import { Stamp } from "../components/Stamp";
import { StrengthTag } from "../components/StrengthTag";
import type { ClientEmissions, FleetReport } from "../fleetApi";
import { gbpFull, litres, tonnes } from "../format";
import { co2Text, litresText } from "../ranges";
import { linkText } from "../sources";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const monthName = (key: string) => `${MONTHS[Number(key.slice(5)) - 1]} ${key.slice(0, 4)}`;

// A label, a dotted leader and a value: one line of the report.
function Line({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <li className="flex flex-wrap items-end gap-x-2 border-b border-rule py-2 last:border-b-0">
      <span className="font-bold">{label}</span>
      <span className="leader" />
      <span className="flex items-center gap-3">{children}</span>
    </li>
  );
}

export function Reports() {
  const [client, setClient] = useState("");
  const clients = useApi<ClientEmissions>("/api/fleet/clients");
  const { data: r, error } = useApi<FleetReport>(`/api/fleet/report${query({ client_id: client || undefined })}`);
  const section = "border-t-2 border-dashed border-rule px-6 py-6";

  const controls = (
    <section className="no-print px-6 pt-6" aria-label="Choose a report">
      <h1 className="font-display text-6xl font-extrabold uppercase leading-[0.95] tracking-wide">Reports</h1>
      <p className="mt-3 max-w-[70ch] text-ink-soft">
        A report you can print or save as a PDF. Every figure lists its sources. Choose the whole company, or a statement for one client farm to
        send with their invoice.
      </p>
      <div className="mt-4 flex flex-wrap items-end gap-4">
        <label className="flex flex-col gap-1 font-mono text-xs uppercase tracking-widest text-ink-soft">
          Report for
          <select value={client} onChange={(e) => setClient(e.target.value)} className="min-h-11 min-w-56 border-2 border-ink bg-paper px-2 font-sans text-base normal-case tracking-normal text-ink">
            <option value="">The whole company</option>
            {(clients.data?.rows ?? []).map((c) => (
              <option key={c.client_id} value={c.client_id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
        <button onClick={() => window.print()} className="btn-solid min-h-11 border-2 border-ink bg-ink px-4 font-mono text-sm uppercase tracking-widest text-paper">
          Print or save as PDF
        </button>
      </div>
    </section>
  );

  if (error && !r) {
    return (
      <>
        {controls}
        <div role="alert" className="mx-6 my-6 border-2 border-ink p-4">
          <p className="font-bold">We could not build the report.</p>
          <p>{error}. Check the API is running and reload this page.</p>
        </div>
      </>
    );
  }
  if (!r) {
    return (
      <>
        {controls}
        <p className="px-6 py-6 text-ink-soft">Building the report...</p>
      </>
    );
  }

  const when = new Date(r.meta.generated_at).toLocaleString("en-GB", { dateStyle: "long", timeStyle: "short" });
  const t = r.totals;

  return (
    <>
      {controls}
      <article aria-labelledby="report-h">
        <header className="px-6 pb-6 pt-8">
          <h2 id="report-h" className="font-display text-4xl font-extrabold uppercase leading-none">
            {r.meta.title}
          </h2>
          <p className="mt-2 font-bold">
            {r.meta.client ?? "The whole company"} · {r.meta.period} · prepared {when}
          </p>
          {r.meta.demo_data && <p className="mt-2 inline-block bg-mark px-3 py-1 font-mono text-xs uppercase tracking-widest text-on-mark">Demo data: illustrative</p>}
          <p className="mt-3 max-w-[65ch]">{r.meta.statement}</p>
        </header>

        <section aria-labelledby="r-totals" className={section}>
          <SectionHead id="r-totals" title="The numbers" tone="solid" />
          <ul>
            <Line label="Fuel burned">
              <span className="num">{litres(t.litres.value ?? 0)} litres</span>
              <Stamp label={t.litres.label} />
            </Line>
            <Line label="Emissions">
              <span className="num">{tonnes(t.co2e_kg.value ?? 0)} CO2e</span>
              <Stamp label={t.co2e_kg.label} />
            </Line>
            <Line label="Fuel cost">
              <span className="num">{gbpFull(t.cost_gbp.value ?? 0)}</span>
              <Stamp label={t.cost_gbp.label} />
            </Line>
            <Line label="Work done">
              <span className="num">
                {litres(t.jobs)} jobs · {litres(t.hours)} engine hours · {litres(t.area_ha)} hectares
              </span>
            </Line>
          </ul>
        </section>

        {r.months && (
          <section aria-labelledby="r-months" className={section}>
            <SectionHead id="r-months" title="Month by month" tone="dashed" />
            <ul>
              {r.months.map((m) => (
                <Line key={m.month} label={monthName(m.month)}>
                  <span className="num">
                    {litres(m.litres.value ?? 0)} L · {tonnes(m.co2e_kg.value ?? 0)} CO2e
                  </span>
                  <Stamp label={m.co2e_kg.label} />
                </Line>
              ))}
            </ul>
          </section>
        )}

        {r.by_site && (
          <section aria-labelledby="r-sites" className={section}>
            <SectionHead id="r-sites" title="By site" tone="dashed" />
            <ul>
              {r.by_site.map((s) => (
                <Line key={s.key} label={s.name}>
                  <span className="num">
                    {litres(s.litres.value ?? 0)} L · {tonnes(s.co2e_kg.value ?? 0)} CO2e
                  </span>
                  <Stamp label={s.litres.label} />
                </Line>
              ))}
            </ul>
          </section>
        )}

        {r.by_client && (
          <section aria-labelledby="r-clients" className={section}>
            <SectionHead id="r-clients" title="By client farm" tone="dashed" />
            <ul>
              {r.by_client.map((c) => (
                <Line key={c.client_id} label={c.name}>
                  <span className="num">
                    {litres(c.litres.value ?? 0)} L · {tonnes(c.co2e_kg.value ?? 0)} CO2e
                  </span>
                  <Stamp label={c.litres.label} />
                </Line>
              ))}
              {r.overhead && (
                <Line label="Company overhead (not charged to a client)">
                  <span className="num">{litres(r.overhead.litres.value ?? 0)} L</span>
                  <Stamp label={r.overhead.litres.label} />
                </Line>
              )}
              {r.unmatched_jobs && (
                <Line label={`Jobs with no matched field (${r.unmatched_jobs.jobs} jobs)`}>
                  <span className="num">{litres(r.unmatched_jobs.litres.value ?? 0)} L</span>
                  <Stamp label={r.unmatched_jobs.litres.label} />
                </Line>
              )}
            </ul>
          </section>
        )}

        {r.findings && (
          <section aria-labelledby="r-findings" className={section}>
            <SectionHead id="r-findings" title="Worth a look" tone="mark" note="to investigate, not proof of a fault" />
            <ul>
              {r.findings.map((f) => (
                <Line key={f.title} label={f.title}>
                  <span className="num">{litres(f.litres.value ?? 0)} {f.litres.unit}</span>
                  <Stamp label={f.litres.label} />
                </Line>
              ))}
            </ul>
          </section>
        )}

        {r.ideas && (
          <section aria-labelledby="r-ideas" className={section}>
            <SectionHead id="r-ideas" title="Ideas that suit the fleet" tone="solid" note="ranges from research · never added together" />
            <ul className="space-y-4">
              {r.ideas.map((i) => (
                <li key={i.intervention_id} className="border-b border-rule pb-4 last:border-b-0">
                  <div className="flex flex-wrap items-center gap-3">
                    <h3 className="font-display text-2xl font-extrabold uppercase leading-none">{i.name}</h3>
                    <StrengthTag robustness={i.robustness} n={i.n_sources} />
                    {i.litres_saved && <Stamp label={i.litres_saved.label} />}
                  </div>
                  <p className="num mt-2">
                    {litresText(i.litres_saved)} a year · {co2Text(i.co2e_avoided_kg)} a year
                  </p>
                </li>
              ))}
            </ul>
          </section>
        )}

        <section aria-labelledby="r-limits" className={section}>
          <SectionHead id="r-limits" title="What we do not know" tone="muted" />
          <ul className="list-disc space-y-2 pl-5">
            {r.limits.map((l) => (
              <li key={l} className="max-w-[70ch]">
                {l}
              </li>
            ))}
          </ul>
        </section>

        <section aria-labelledby="r-labels" className={section}>
          <SectionHead id="r-labels" title="What the labels mean" tone="dashed" />
          <ul className="space-y-3">
            {r.labels.map((l) => (
              <li key={l.label} className="flex flex-wrap items-center gap-4">
                <Stamp label={l.label} />
                <span className="max-w-[65ch]">{l.meaning}</span>
              </li>
            ))}
          </ul>
        </section>

        <section aria-labelledby="r-method" className={section}>
          <SectionHead id="r-method" title="How it was worked out" tone="solid" />
          <Rich text={r.method} />
        </section>

        <section aria-labelledby="r-sources" className={section}>
          <SectionHead id="r-sources" title="Sources" tone="dashed" />
          <ul className="space-y-3">
            {r.sources.map((s) => (
              <li key={s.source_id} className="text-sm">
                <span className="font-bold">{s.title}</span>
                <span className="block text-ink-soft">
                  {[s.publisher_or_authors, s.year].filter(Boolean).join(", ")} · {linkText(s.link_status)}
                </span>
                {s.url && <span className="block break-all">{s.url}</span>}
              </li>
            ))}
          </ul>
          <p className="mt-4 max-w-[75ch] text-sm text-ink-soft">{r.attribution}</p>
        </section>
      </article>
    </>
  );
}
